# -*- coding: utf-8 -*-
"""
Аналитика событий сайта (минимально-инвазивный лог).

Сейчас содержит один публичный метод — log_concierge_event(...). Запись идёт
в JSONL-файл logs/concierge.jsonl (по одному JSON-объекту на строку).
Это даёт нам:
  • моментальную видимость без БД-миграции,
  • простой грeп / pandas-парсинг для последующего обогащения site_kb.json.

При необходимости можно завести таблицу AnalyticsEvent в models.py — public
API этого модуля стабилен и не сломается.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

_LOCK = Lock()
_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs'
)
_CONCIERGE_LOG = os.path.join(_LOG_DIR, 'concierge.jsonl')


def _ensure_log_dir() -> None:
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
    except Exception as e:
        logger.warning('Cannot create logs dir %s: %s', _LOG_DIR, e)


def log_concierge_event(
    *,
    message: str,
    intent_id: Optional[str],
    source: str,
    current_url: Optional[str] = None,
    user_id: Optional[int] = None,
    ip: Optional[str] = None,
    matched: bool = False,
) -> None:
    """Зафиксировать одно обращение к Site Concierge.

    :param message: оригинальный текст вопроса.
    :param intent_id: идентификатор intent из site_kb.json, если был match.
    :param source: 'kb' | 'llm' | 'redirect' | 'fallback' | 'empty'.
    :param current_url: URL страницы, с которой пришёл пользователь.
    :param user_id: id пользователя, если авторизован.
    :param ip: IP клиента (с уважением к X-Forwarded-For).
    :param matched: True, если ответ из KB; False — если LLM/fallback.
    """
    _ensure_log_dir()
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": "concierge_ask",
        "message": (message or '')[:500],
        "intent_id": intent_id,
        "matched": matched,
        "source": source,
        "current_url": (current_url or '')[:300],
        "user_id": user_id,
        "ip": ip,
    }
    line = json.dumps(event, ensure_ascii=False)
    try:
        with _LOCK:
            with open(_CONCIERGE_LOG, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
    except Exception as e:
        logger.warning('Failed to write concierge analytics: %s', e)
