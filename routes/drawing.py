# -*- coding: utf-8 -*-
# Blueprint "/drawing" — geometry drawing playground, code-gen pipeline.
#
# Endpoints
# ---------
#   GET  /drawing                — render the playground page.
#   POST /api/drawing/generate   — JSON body: problem -> JSON with image.
#
# The heavy lifting lives in services.drawing_service.generate_drawing(),
# which (1) hashes & looks up the cache, (2) asks Claude Sonnet to author
# matplotlib Python, (3) executes that Python inside services.sandbox,
# (4) repairs up to 2 times on failure, (5) writes the PNG to cache.
#
# Every call is logged to models.DrawingGeneration for analytics. The
# logger never blocks the response: failures there are swallowed.

from __future__ import annotations

import base64
import json
import logging
import os
import time
import uuid
from collections import defaultdict
from threading import Lock

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    url_for,
)

try:
    from flask_login import current_user  # type: ignore
except Exception:  # pragma: no cover
    current_user = None  # type: ignore

from services.drawing_service import (
    generate_drawing,
    DrawingResult,
    SYSTEM_PROMPT,  # noqa: F401  (re-exported for debugging)
)
from services.drawing_async import run_drawing_async, get_task_status
from services.sandbox import (
    SandboxError,
    SandboxRejected,
    SandboxTimeout,
)
from services.openrouter_client import OpenRouterError

logger = logging.getLogger(__name__)

drawing_bp = Blueprint("drawing", __name__)

# ── Async task store (in-memory, TTL 30 min) ─────────────────────────────────
_TASK_STORE: dict = {}
_task_store_lock = Lock()
_TASK_TTL = 1800


def _task_store_cleanup() -> None:
    now = time.time()
    with _task_store_lock:
        expired = [k for k, v in _TASK_STORE.items()
                   if now - v.get("created_at", 0) > _TASK_TTL]
        for k in expired:
            del _TASK_STORE[k]


def _task_set(task_id: str, **kwargs) -> None:
    with _task_store_lock:
        if task_id not in _TASK_STORE:
            _TASK_STORE[task_id] = {"created_at": time.time()}
        _TASK_STORE[task_id].update(kwargs)


def _task_get(task_id: str):
    with _task_store_lock:
        return dict(_TASK_STORE[task_id]) if task_id in _TASK_STORE else None


# ─── Rate limit (in-memory) ───────────────────────────────────────────────────

_RATE_LIMIT_MAX = 10
_RATE_LIMIT_WINDOW = 3600
_rate_log: dict[str, list[float]] = defaultdict(list)
_rate_lock = Lock()


def _rate_key() -> str:
    try:
        if current_user is not None and getattr(current_user, "is_authenticated", False):
            uid = getattr(current_user, "id", None)
            if uid is not None:
                return f"user:{uid}"
    except Exception:
        pass
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "anon")
    return f"ip:{ip.split(',')[0].strip()}"


def _rate_check() -> tuple[bool, int]:
    key = _rate_key()
    now = time.time()
    with _rate_lock:
        bucket = [t for t in _rate_log[key] if now - t < _RATE_LIMIT_WINDOW]
        _rate_log[key] = bucket
        if len(bucket) >= _RATE_LIMIT_MAX:
            retry_after = int(_RATE_LIMIT_WINDOW - (now - bucket[0])) + 1
            return False, max(retry_after, 1)
        bucket.append(now)
        return True, 0


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _generated_dir() -> str:
    root = current_app.root_path
    path = os.path.join(root, "static", "generated")
    os.makedirs(path, exist_ok=True)
    return path


def _save_png(image_bytes: bytes) -> tuple[str, str]:
    """Persist PNG to static/generated and return (url, absolute_path)."""
    fname = f"drawing_{uuid.uuid4().hex}.png"
    abs_path = os.path.join(_generated_dir(), fname)
    with open(abs_path, "wb") as f:
        f.write(image_bytes)
    return url_for("static", filename=f"generated/{fname}"), abs_path


def _log_to_db(
    *,
    problem: str,
    status: str,
    result: DrawingResult | None = None,
    error: str | None = None,
    image_path: str | None = None,
) -> None:
    """Best-effort write to models.DrawingGeneration."""
    try:
        import hashlib
        import json as _json
        from dataclasses import asdict
        from models import db, DrawingGeneration  # local import to avoid cycles
        sha = hashlib.sha256(problem.encode("utf-8")).hexdigest()

        uid = None
        try:
            if current_user is not None and getattr(current_user, "is_authenticated", False):
                uid = getattr(current_user, "id", None)
        except Exception:
            pass

        # Serialize critique findings if present.
        findings_json = None
        if result and getattr(result, "critique_findings", None):
            try:
                findings_json = _json.dumps(
                    [asdict(f) for f in result.critique_findings],
                    ensure_ascii=False,
                )[:10000]
            except Exception:
                findings_json = None

        row = DrawingGeneration(
            user_id=uid,
            problem_sha256=sha,
            problem=problem[:5000],
            generated_code=(result.code if result else None),
            model=(result.model if result else None),
            status=status,
            error=(error[:4000] if error else None),
            repair_iters=(result.repair_iters if result else 0),
            render_ms=(result.render_ms if result else None),
            cost_usd=float(result.cost_usd if result else 0.0),
            image_path=image_path,
            image_size=(len(result.image_bytes) if result else None),
            critique_rounds=(result.critique_rounds if result else 0),
            critique_accepted=(result.critique_accepted if result else 0),
            critique_rejected=(result.critique_rejected if result else 0),
            critique_findings_json=findings_json,
        )
        db.session.add(row)
        db.session.commit()
    except Exception as e:
        logger.warning("[drawing] failed to log DrawingGeneration row: %s", e)


# ─── Routes ───────────────────────────────────────────────────────────────────

@drawing_bp.route("/mock-payment", methods=["GET"])
def mock_payment_page():
    """Тестовая страница оплаты. plan=unlimited|topup."""
    plan = (request.args.get('plan') or 'topup').strip().lower()
    if plan not in ('unlimited', 'topup'):
        plan = 'topup'
    return render_template('mock_payment.html', plan=plan)


@drawing_bp.route("/drawing", methods=["GET"])
def drawing_page():
    # Generation limit info for the template banner
    try:
        from app import _get_remaining_generations
        remaining = _get_remaining_generations(current_user)
        gens_unlimited = bool(current_user.gens_unlimited) if current_user else False
        gens_label = '♾️ Безлимит' if gens_unlimited else f'{remaining} / день'
    except Exception:
        remaining = 0
        gens_unlimited = False
        gens_label = '—'

    return render_template("drawing.html",
                           remaining_generations=remaining,
                           gens_unlimited=gens_unlimited,
                           gens_label=gens_label)


@drawing_bp.route("/whiteboard", methods=["GET"])
def whiteboard_page():
    """Отдельная страница «Доска» (бесконечный whiteboard) — без AI-генератора.

    Используется как landing для приглашений в видеозвонок:
    `wb_call_listener.js` редиректит сюда с `?room=<code>`.
    Теперь также поддерживает `?board=<id>` для per-board localStorage.
    """
    board_id = request.args.get("board", "default")
    room = request.args.get("room", "")
    conv = request.args.get("conv", "")
    return render_template("whiteboard.html", board_id=board_id, room=room, conv=conv)


@drawing_bp.route("/api/drawing/status/<task_id>", methods=["GET"])
def api_drawing_status(task_id: str):
    """Poll the status of an async drawing generation task."""
    _task_store_cleanup()
    task = get_task_status(task_id)
    if task is None:
        return jsonify({"error": "task not found"}), 404
    status = task.get("status", "pending")
    if status == "completed":
        return jsonify({"task_id": task_id, "status": "completed",
                        "result": task.get("result")})
    elif status == "error":
        return jsonify({"task_id": task_id, "status": "error",
                        "error": task.get("error", "unknown error")})
    return jsonify({"task_id": task_id, "status": status})


@drawing_bp.route("/api/drawing/generate", methods=["POST"])
def api_drawing_generate():
    # Force UTF-8 decoding of the body (defence vs proxy mojibake).
    raw = request.get_data(cache=False, as_text=False) or b""
    try:
        logger.info("[drawing] POST /api/drawing/generate body=%d bytes ct=%s",
                    len(raw), request.headers.get("Content-Type", "?"))
    except Exception:
        pass
    try:
        text = raw.decode("utf-8")
        data = json.loads(text) if text else {}
    except Exception as _e:
        logger.warning("[drawing] body decode failed (%s), retrying via flask", _e)
        data = request.get_json(silent=True) or {}

    problem = (data.get("problem") or "").strip()
    # Optional photo of the task (data URL or bare base64).  If present
    # we run vision-OCR first and either use it as the problem text or
    # combine it with the typed text below.
    raw_image = data.get("image_b64") or data.get("image") or ""
    logger.info("[drawing] keys=%s problem_len=%d image_present=%s image_len=%d",
                list(data.keys()) if isinstance(data, dict) else type(data).__name__,
                len(problem),
                bool(raw_image),
                len(raw_image) if isinstance(raw_image, str) else 0)
    if isinstance(raw_image, str):
        raw_image = raw_image.strip()
    else:
        raw_image = ""
    image_mime = "image/png"
    image_bytes: bytes | None = None
    if raw_image:
        try:
            payload = raw_image
            if payload.startswith("data:"):
                # data:image/jpeg;base64,XXXX
                header, _, b64body = payload.partition(",")
                if ";base64" in header.lower():
                    payload = b64body
                # extract MIME if present
                if header.startswith("data:") and ";" in header:
                    image_mime = header[5:].split(";", 1)[0] or "image/png"
            image_bytes = base64.b64decode(payload, validate=False)
            # 8 MB upper bound to protect Gemini from abuse
            if len(image_bytes) > 8 * 1024 * 1024:
                return jsonify({
                    "error": (
                        "Изображение слишком большое (макс 8 МБ). "
                        "Уменьши размер скриншота."
                    )
                }), 400
            if len(image_bytes) < 200:
                image_bytes = None
        except Exception as _e:  # noqa: BLE001
            return jsonify({
                "error": "Не удалось прочитать изображение (битый base64)."
            }), 400

    # When the user clicks "Regenerate without cache" we want to force
    # a full pipeline run even if the same problem text has been seen
    # before.  Accepted as truthy bool/int/string.
    _raw_bypass = data.get("bypass_cache", False)
    if isinstance(_raw_bypass, bool):
        bypass_cache = _raw_bypass
    elif isinstance(_raw_bypass, (int, float)):
        bypass_cache = bool(_raw_bypass)
    elif isinstance(_raw_bypass, str):
        bypass_cache = _raw_bypass.strip().lower() in ("1", "true", "yes", "on")
    else:
        bypass_cache = False

    # OCR stage: if a photo was attached we run vision-OCR before we
    # validate the textual length.  The OCR result is concatenated with
    # whatever the student typed (typed text wins as the leading part,
    # since students usually type a comment like "see image" + image).
    ocr_used = False
    ocr_text: str | None = None
    if image_bytes is not None:
        logger.info("[drawing] running OCR on image %d bytes mime=%s",
                    len(image_bytes), image_mime)
        try:
            from services.drawing_ocr import ocr_problem_image
        except Exception as _e:  # pragma: no cover
            ocr_problem_image = None  # type: ignore[assignment]
            logger.warning("[drawing] OCR module import failed: %s", _e)
        if ocr_problem_image is not None:
            ocr_text, _ocr_cost = ocr_problem_image(image_bytes, mime=image_mime)
            ocr_used = bool(ocr_text)
            logger.info("[drawing] OCR done used=%s text_len=%d cost=$%.4f",
                        ocr_used, len(ocr_text or ""), _ocr_cost)
            if ocr_text:
                if problem:
                    problem = (problem + "\n\n" + ocr_text).strip()
                else:
                    problem = ocr_text
            elif not problem:
                return jsonify({
                    "error": (
                        "Не удалось распознать условие на фото. "
                        "Проверь, что текст задачи виден и сделан скриншот "
                        "достаточного разрешения, или напечатай условие "
                        "вручную."
                    )
                }), 400
    else:
        if raw_image:
            logger.warning("[drawing] image_b64 was present but decoded to None "
                           "(len_b64=%d) — likely too small or invalid base64",
                           len(raw_image))

    if not problem:
        return jsonify({"error": "Условие задачи не указано."}), 400
    if len(problem) < 10:
        return jsonify({"error": "Условие слишком короткое — минимум 10 символов."}), 400
    if len(problem) > 4000:
        return jsonify({"error": "Условие слишком длинное — максимум 4000 символов."}), 400

    allowed, retry_after = _rate_check()
    if not allowed:
        resp = jsonify({
            "error": (
                "Превышен лимит: 10 чертежей в час. "
                f"Попробуйте через {retry_after // 60 + 1} мин."
            )
        })
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp

    app_root = current_app.root_path

    # Launch generation in a background thread.
    # Returns task_id immediately; client polls GET /api/drawing/status/<task_id>
    task_id = run_drawing_async(
        problem, app_root, bypass_cache,
        _save_png, _log_to_db,
    )
    return jsonify(task_id=task_id, status="processing"), 202

