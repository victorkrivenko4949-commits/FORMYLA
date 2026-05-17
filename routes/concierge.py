# -*- coding: utf-8 -*-
"""
Blueprint: /api/concierge/* — endpoints for the Site Concierge widget.

Routes:
    POST /api/concierge/ask    — задать вопрос (rate-limit 30/hour/IP)
    GET  /api/concierge/intents — список топ-intents для quick replies

Виджет привязан к `templates/partials/site_concierge.html` и
`static/js/site_concierge.js`.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from threading import Lock

from flask import Blueprint, jsonify, request
from flask_login import current_user

from services.site_concierge import answer_site_question, get_top_intents
from services.analytics import log_concierge_event

logger = logging.getLogger(__name__)

concierge_bp = Blueprint('concierge', __name__, url_prefix='/api/concierge')


# ── Rate limiter ─────────────────────────────────────────────────────────────
# In-memory sliding-window per-IP. Free-tier ОК, на проде уйдёт за Redis.

_RATE_WINDOW_SEC = 3600  # 1 час
_RATE_LIMIT = 30
_rate_log: dict[str, deque] = defaultdict(deque)
_rate_lock = Lock()


def _client_ip() -> str:
    """Извлечь IP клиента c уважением к X-Forwarded-For (1 proxy hop)."""
    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        # Первый IP в цепочке — оригинальный клиент.
        return xff.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _check_rate_limit(ip: str) -> tuple[bool, int]:
    """True если запрос разрешён, плюс remaining (для X-RateLimit-Remaining)."""
    now = time.time()
    cutoff = now - _RATE_WINDOW_SEC
    with _rate_lock:
        log = _rate_log[ip]
        # Снимаем устаревшие записи.
        while log and log[0] < cutoff:
            log.popleft()
        if len(log) >= _RATE_LIMIT:
            return False, 0
        log.append(now)
        return True, _RATE_LIMIT - len(log)


# ── Endpoints ────────────────────────────────────────────────────────────────

@concierge_bp.route('/intents', methods=['GET'])
def list_intents():
    """Возвращает список топ-intents для отрисовки Quick Replies."""
    items = get_top_intents(limit=10)
    return jsonify({"intents": items})


@concierge_bp.route('/ask', methods=['POST'])
def ask():
    """Главный endpoint: пользователь задаёт вопрос → отвечаем."""
    ip = _client_ip()
    allowed, remaining = _check_rate_limit(ip)
    if not allowed:
        return (
            jsonify({
                "error": "rate_limit",
                "message": "Слишком много запросов. Попробуй через час или напиши в поддержку через /about.",
            }),
            429,
            {"Retry-After": str(_RATE_WINDOW_SEC)},
        )

    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    current_url = (data.get('current_url') or '').strip()

    if not message:
        return jsonify({
            "answer": "Напиши, что хочешь сделать — подскажу, куда нажать.",
            "suggested_actions": [],
            "source": "empty",
        }), 200

    if len(message) > 500:
        message = message[:500]

    context = {
        "current_url": current_url,
        "user_id": getattr(current_user, 'id', None) if current_user.is_authenticated else None,
        "ip": ip,
    }

    try:
        result = answer_site_question(message, context=context)
    except Exception as e:
        logger.exception('answer_site_question failed: %s', e)
        return jsonify({
            "answer": "Что-то пошло не так. Попробуй ещё раз через минуту.",
            "suggested_actions": [],
            "source": "error",
        }), 200

    # Аналитика — best-effort, не валит запрос.
    try:
        log_concierge_event(
            message=message,
            intent_id=result.get('intent_id'),
            source=result.get('source', 'unknown'),
            current_url=current_url,
            user_id=context['user_id'],
            ip=ip,
            matched=result.get('source') == 'kb',
        )
    except Exception as e:
        logger.warning('analytics log failed: %s', e)

    response = jsonify({
        "answer": result.get('answer', ''),
        "suggested_actions": result.get('suggested_actions') or [],
        "source": result.get('source', 'unknown'),
    })
    response.headers['X-RateLimit-Remaining'] = str(remaining)
    return response, 200
