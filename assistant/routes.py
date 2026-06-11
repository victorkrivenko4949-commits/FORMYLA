# -*- coding: utf-8 -*-
"""Flask blueprint for the FORMYLA Site Assistant.

Routes:
    POST /api/assistant            — new canonical endpoint (TZ section 5)
    POST /api/concierge/ask        — legacy-compatible alias for the
                                     existing widget in templates/about.html
    GET  /api/concierge/intents    — legacy stub so the old JS keeps working

The legacy aliases let us replace the old ``routes/concierge.py`` without
touching the front-end shipped on the live site.

All routes are read-only / rate-limited and never raise — on any failure
they return ``200`` with ``{ok: false, answer: "<safe>"}``.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Tuple

from flask import Blueprint, jsonify, request

from .service import answer as service_answer

logger = logging.getLogger(__name__)

assistant_bp = Blueprint("assistant", __name__)


# ---------------------------------------------------------------------------
# Simple in-memory rate limiter (per-IP, sliding 1h window, 30 reqs).
# Render single-instance setup; for multi-worker swap to Redis later.
# ---------------------------------------------------------------------------
_RATE_WINDOW_SEC = 3600
_RATE_LIMIT = 30
_rate_log: "dict[str, deque]" = defaultdict(deque)
_rate_lock = Lock()


def _client_ip() -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _check_rate_limit(ip: str) -> Tuple[bool, int]:
    now = time.time()
    cutoff = now - _RATE_WINDOW_SEC
    with _rate_lock:
        log = _rate_log[ip]
        while log and log[0] < cutoff:
            log.popleft()
        if len(log) >= _RATE_LIMIT:
            return False, 0
        log.append(now)
        return True, _RATE_LIMIT - len(log)


_RATE_LIMITED = {
    "ok": False,
    "answer": "Слишком много запросов. Попробуй через минуту.",
    "suggested_actions": [],
}

_ERROR_PAYLOAD = {
    "ok": False,
    "answer": "Сейчас помощник временно недоступен. Попробуй позже.",
    "suggested_actions": [],
}


def _process(message: str) -> dict:
    """Run the service pipeline; never raise."""
    try:
        result = service_answer(message)
        return {
            "ok": bool(result.get("ok", True)),
            "answer": result.get("answer") or "",
            "suggested_actions": result.get("suggested_actions") or [],
            "category": result.get("category"),
        }
    except Exception as e:
        logger.exception("assistant.routes: service_answer crashed: %s", e)
        return dict(_ERROR_PAYLOAD)


# ---------------------------------------------------------------------------
# Canonical endpoint (TZ §5)
# ---------------------------------------------------------------------------
@assistant_bp.route("/api/assistant", methods=["POST"])
def post_assistant():
    ip = _client_ip()
    allowed, remaining = _check_rate_limit(ip)
    if not allowed:
        resp = jsonify(_RATE_LIMITED)
        resp.headers["Retry-After"] = str(_RATE_WINDOW_SEC)
        return resp, 429

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if len(message) > 1000:
        message = message[:1000]

    if not message:
        return jsonify({
            "ok": True,
            "answer": (
                "Напиши, что хочешь сделать: пройти адаптивный тест, "
                "посмотреть прогресс, открыть задачи или узнать про тарифы."
            ),
            "suggested_actions": [
                {"label": "Пройти адаптивный тест", "url": "/adaptive-test"},
                {"label": "Открыть пробники",      "url": "/probniki"},
            ],
        })

    payload = _process(message)
    resp = jsonify(payload)
    resp.headers["X-RateLimit-Remaining"] = str(remaining)
    return resp


# ---------------------------------------------------------------------------
# Legacy aliases — keep the old widget on /about working without changes.
# Old contract (services/site_concierge → routes/concierge.py):
#     POST /api/concierge/ask  → { answer, suggested_actions, source }
#     GET  /api/concierge/intents → { intents: [...] }
# ---------------------------------------------------------------------------
@assistant_bp.route("/api/concierge/ask", methods=["POST"])
def legacy_concierge_ask():
    ip = _client_ip()
    allowed, remaining = _check_rate_limit(ip)
    if not allowed:
        return (
            jsonify({
                "error": "rate_limit",
                "message": "Слишком много запросов. Попробуй позже.",
            }),
            429,
            {"Retry-After": str(_RATE_WINDOW_SEC)},
        )

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if len(message) > 1000:
        message = message[:1000]

    if not message:
        return jsonify({
            "answer": "Напиши, что хочешь сделать — подскажу, куда нажать.",
            "suggested_actions": [],
            "source": "empty",
        })

    payload = _process(message)
    resp = jsonify({
        "answer": payload.get("answer", ""),
        "suggested_actions": payload.get("suggested_actions") or [],
        # "source" is required by the old JS; map to category for analytics.
        "source": payload.get("category") or "llm",
    })
    resp.headers["X-RateLimit-Remaining"] = str(remaining)
    return resp


@assistant_bp.route("/api/concierge/intents", methods=["GET"])
def legacy_concierge_intents():
    """Return the seeded categories as quick-reply suggestions.

    Kept for backward compatibility with the old widget; the new
    ``/api/assistant`` flow does not depend on this.
    """
    try:
        from .kb import all_active
        items = [
            {
                "id": r.get("category"),
                "intent": r.get("title"),
                "icon": "💬",
            }
            for r in all_active()
            if r.get("category") and r.get("title")
        ]
    except Exception as e:  # pragma: no cover
        logger.warning("legacy_concierge_intents: %s", e)
        items = []
    return jsonify({"intents": items[:10]})


__all__ = ["assistant_bp"]
