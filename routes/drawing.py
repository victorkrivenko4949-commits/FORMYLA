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
from services.sandbox import (
    SandboxError,
    SandboxRejected,
    SandboxTimeout,
)
from services.openrouter_client import OpenRouterError

logger = logging.getLogger(__name__)

drawing_bp = Blueprint("drawing", __name__)


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

@drawing_bp.route("/drawing", methods=["GET"])
def drawing_page():
    return render_template("drawing.html")


@drawing_bp.route("/whiteboard", methods=["GET"])
def whiteboard_page():
    """Отдельная страница «Доска» (бесконечный whiteboard) — без AI-генератора.

    Используется как landing для приглашений в видеозвонок:
    `wb_call_listener.js` редиректит сюда с `?room=<code>`.
    """
    return render_template("whiteboard.html")


@drawing_bp.route("/api/drawing/generate", methods=["POST"])
def api_drawing_generate():
    # Force UTF-8 decoding of the body (defence vs proxy mojibake).
    raw = request.get_data(cache=False, as_text=False) or b""
    logger.info("[drawing] POST /api/drawing/generate body=%d bytes ct=%s",
                len(raw), request.headers.get("Content-Type", "?"))
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

    try:
        result = generate_drawing(
            problem,
            app_root=app_root,
            use_cache=not bypass_cache,
        )
    except SandboxRejected as e:
        logger.error("[drawing] sandbox rejected: %s", e)
        _log_to_db(problem=problem, status="rejected", error=str(e))
        return jsonify({
            "error": "Сгенерированный код не прошёл проверку безопасности.",
            "detail": str(e),
            "stage": "sandbox.validate",
        }), 502
    except SandboxTimeout as e:
        logger.error("[drawing] sandbox timeout: %s", e)
        _log_to_db(problem=problem, status="timeout", error=str(e))
        return jsonify({
            "error": "Построение чертежа заняло слишком много времени.",
            "detail": str(e),
            "stage": "sandbox.run",
        }), 502
    except SandboxError as e:
        logger.error("[drawing] sandbox error: %s", e)
        _log_to_db(problem=problem, status="error", error=str(e))
        return jsonify({
            "error": "Не удалось построить чертёж.",
            "detail": str(e)[:1500],
            "stage": "sandbox.run",
        }), 502
    except OpenRouterError as e:
        logger.error("[drawing] openrouter error: %s", e)
        _log_to_db(problem=problem, status="error", error=str(e))
        return jsonify({
            "error": "Сервис генерации временно недоступен.",
            "detail": str(e),
            "stage": "llm",
        }), 502
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:  # pragma: no cover
        logger.exception("[drawing] unexpected error")
        _log_to_db(problem=problem, status="error", error=str(e))
        return jsonify({
            "error": "Внутренняя ошибка сервера.",
            "detail": str(e),
        }), 500

    # Persist to /static/generated/* for the <img> tag.
    image_url: str | None = None
    image_abs: str | None = None
    try:
        image_url, image_abs = _save_png(result.image_bytes)
    except Exception as e:
        logger.warning("[drawing] failed to persist PNG: %s", e)

    status = "cache_hit" if result.cache_hit else "ok"
    _log_to_db(
        problem=problem,
        status=status,
        result=result,
        image_path=image_abs,
    )

    image_b64 = base64.b64encode(result.image_bytes).decode("ascii")

    return jsonify({
        "image_url": image_url,
        "image_b64": image_b64,
        "data_url": "data:image/png;base64," + image_b64,
        "model": result.model,
        "cost_usd": result.cost_usd,
        "render_ms": result.render_ms,
        "cache_hit": result.cache_hit,
        "repair_iters": result.repair_iters,
        "critique_rounds": result.critique_rounds,
        "critique_accepted": result.critique_accepted,
        "critique_rejected": result.critique_rejected,
        # Avoid leaking source code by default; admins can read it from
        # DrawingGeneration in the DB.
    })
