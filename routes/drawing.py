# -*- coding: utf-8 -*-
"""
Blueprint: «Чертёж» — построение геометрических чертежей по тексту задачи.

Архитектура (гибридная, без image-generation)
---------------------------------------------
1.  LLM (через services.geometry_spec) парсит условие в строгий JSON
    с вершинами, отрезками, заданными длинами/углами и метками равенства.
2.  Python в том же сервисе детерминированно вычисляет координаты вершин
    (теорема косинусов / трилатерация / SAS).
3.  services.geometry_renderer через matplotlib рисует чистый PNG 1024×1024:
    чёрные линии на белом фоне, аккуратные подписи, без лишних построений.

Это устраняет проблемы LLM-«художников» (кривые буквы, лишние линии,
ошибочные пропорции): нейросеть отвечает только за разбор условия,
рисует — детерминированный код.

Endpoints
---------
  GET  /drawing                  — страница ввода условия + результат.
  POST /api/drawing/generate     — JSON {"problem": "..."} →
                                   {"image_url": "/static/generated/...png",
                                    "image_b64": "<base64 PNG>",
                                    "data_url":  "data:image/png;base64,...",
                                    "spec":      {...рендер-спека...},
                                    "model":     "anthropic/claude-sonnet-4.5",
                                    "cost_usd":  0.0042}

Безопасность
------------
* Валидация длины problem: 10..2000 символов.
* In-memory rate-limit: 10 генераций / час на user_id (или IP).
* PNG складывается в static/generated/<uuid>.png и возвращается также
  base64 — чтобы фронт показал картинку без второго HTTP-запроса.
"""

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

from services.geometry_renderer import (
    render_spec_to_png,
    GeometrySpecError,
)
from services.geometry_spec import (
    parse_problem_to_spec,
    build_render_spec,
    GeometryParseError,
)
from services.openrouter_client import OpenRouterError

logger = logging.getLogger(__name__)

drawing_bp = Blueprint("drawing", __name__)


# ─── Rate limiter (in-memory, per-user / per-IP) ──────────────────────────────

_RATE_LIMIT_MAX = 10           # запросов
_RATE_LIMIT_WINDOW = 3600      # за 1 час (секунд)
_rate_log: dict[str, list[float]] = defaultdict(list)
_rate_lock = Lock()


def _rate_key() -> str:
    """Stable key for the current requester (user-id or IP fallback)."""
    try:
        if current_user is not None and getattr(current_user, "is_authenticated", False):
            uid = getattr(current_user, "id", None)
            if uid is not None:
                return f"user:{uid}"
    except Exception:
        pass
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "anon")
    ip = ip.split(",")[0].strip()
    return f"ip:{ip}"


def _rate_check() -> tuple[bool, int]:
    """Returns (allowed, retry_after_sec). retry_after_sec is 0 if allowed."""
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
    """Absolute path to static/generated, creating it on first use."""
    root = current_app.root_path
    path = os.path.join(root, "static", "generated")
    os.makedirs(path, exist_ok=True)
    return path


def _save_png(image_bytes: bytes) -> str:
    """Write PNG to static/generated/<uuid>.png and return its URL."""
    fname = f"drawing_{uuid.uuid4().hex}.png"
    out_path = os.path.join(_generated_dir(), fname)
    with open(out_path, "wb") as f:
        f.write(image_bytes)
    return url_for("static", filename=f"generated/{fname}")


def _strip_meta(spec: dict) -> dict:
    """Drop internal _meta keys from the spec before returning to the client."""
    return {k: v for k, v in spec.items() if not k.startswith("_")}


# ─── Routes ───────────────────────────────────────────────────────────────────

@drawing_bp.route("/drawing", methods=["GET"])
def drawing_page():
    """Render the drawing playground page."""
    return render_template("drawing.html")


@drawing_bp.route("/api/drawing/generate", methods=["POST"])
def api_drawing_generate():
    """Build a geometry drawing from a problem statement (hybrid pipeline)."""
    # Read body explicitly as UTF-8 to avoid mojibake on Windows / proxies.
    raw = request.get_data(cache=False, as_text=False) or b""
    try:
        text = raw.decode("utf-8")
        data = json.loads(text) if text else {}
    except Exception:
        data = request.get_json(silent=True) or {}

    problem = (data.get("problem") or "").strip()

    # ── Validation ────────────────────────────────────────────────────────
    if not problem:
        return jsonify({"error": "Условие задачи не указано."}), 400
    if len(problem) < 10:
        return jsonify({
            "error": "Условие слишком короткое — нужно хотя бы 10 символов."
        }), 400
    if len(problem) > 2000:
        return jsonify({
            "error": "Условие слишком длинное — максимум 2000 символов."
        }), 400

    # ── Rate limit ────────────────────────────────────────────────────────
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

    # ── 1) LLM → parsed JSON ──────────────────────────────────────────────
    try:
        parsed = parse_problem_to_spec(problem)
    except GeometryParseError as e:
        logger.error(f"[drawing] parse error: {e}")
        return jsonify({
            "error": "Не удалось разобрать условие задачи.",
            "detail": str(e),
            "stage": "parse",
        }), 502
    except OpenRouterError as e:
        logger.error(f"[drawing] openrouter error: {e}")
        return jsonify({
            "error": "Сервис разбора недоступен. Попробуйте ещё раз.",
            "detail": str(e),
            "stage": "parse",
        }), 502

    meta = (parsed.get("_meta") or {}) if isinstance(parsed, dict) else {}

    # ── 2) Deterministic coordinate solver ────────────────────────────────
    try:
        spec = build_render_spec(parsed)
    except GeometryParseError as e:
        logger.error(f"[drawing] build error: {e}")
        return jsonify({
            "error": "В условии не хватает данных для построения чертежа.",
            "detail": str(e),
            "stage": "build",
            "parsed": parsed,
        }), 422

    # ── 3) Matplotlib render ──────────────────────────────────────────────
    try:
        image_bytes = render_spec_to_png(spec)
    except GeometrySpecError as e:
        logger.error(f"[drawing] render spec error: {e}")
        return jsonify({
            "error": "Ошибка в структуре чертежа.",
            "detail": str(e),
            "stage": "render",
            "spec": _strip_meta(spec),
        }), 422
    except Exception as e:  # pragma: no cover
        logger.exception(f"[drawing] render failed: {e}")
        return jsonify({
            "error": "Не удалось отрисовать чертёж.",
            "detail": str(e),
            "stage": "render",
        }), 500

    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    image_url = None
    try:
        image_url = _save_png(image_bytes)
    except Exception as e:
        logger.warning(f"[drawing] failed to persist PNG: {e}")

    cost = float(meta.get("cost_usd") or 0.0)
    model = meta.get("model")
    logger.info(
        f"[drawing] OK model={model} bytes={len(image_bytes)} "
        f"user={_rate_key()} cost_usd={cost:.4f}"
    )

    return jsonify({
        "image_url": image_url,
        "image_b64": image_b64,
        "data_url": f"data:image/png;base64,{image_b64}",
        "spec": _strip_meta(spec),
        "model": model,
        "cost_usd": cost,
    })
