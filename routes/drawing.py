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


@drawing_bp.route("/api/drawing/generate", methods=["POST"])
def api_drawing_generate():
    # Force UTF-8 decoding of the body (defence vs proxy mojibake).
    raw = request.get_data(cache=False, as_text=False) or b""
    try:
        text = raw.decode("utf-8")
        data = json.loads(text) if text else {}
    except Exception:
        data = request.get_json(silent=True) or {}

    problem = (data.get("problem") or "").strip()

    if not problem:
        return jsonify({"error": "Условие задачи не указано."}), 400
    if len(problem) < 10:
        return jsonify({"error": "Условие слишком короткое — минимум 10 символов."}), 400
    if len(problem) > 2000:
        return jsonify({"error": "Условие слишком длинное — максимум 2000 символов."}), 400

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
        result = generate_drawing(problem, app_root=app_root, use_cache=True)
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
