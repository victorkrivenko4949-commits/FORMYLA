# -*- coding: utf-8 -*-
"""Вставка блоков «Куратор: план на сегодня» и «Метод недели» на страницу
задач дня без правки 86-килобайтного шаблона: after_request добавляет
<script> перед </body> на HTML-ответе GET /daily_tasks — только для
аккаунтов из METHOD_WEEK_ALLOWED_USERS (тестовый период)."""
from __future__ import annotations

import logging
import os

from flask import request

logger = logging.getLogger(__name__)


def _ui_enabled() -> bool:
    # Временно выключено (2026-10-22): по просьбе владельца блок «Куратор» +
    # «Метод недели» с 3 задачами убран со страницы задач дня даже для
    # тестовых аккаунтов. Вернуть: METHOD_WEEK_UI_ENABLED=1.
    # API /method_week/* продолжает работать.
    return os.environ.get('METHOD_WEEK_UI_ENABLED', '0') == '1'

_SNIPPET = ('<div id="mw-root"></div>'
            '<script src="/static/method_week.js?v=1" defer></script></body>')


def install_ui_injector(app) -> None:
    @app.after_request
    def _mw_inject(resp):
        try:
            path = (request.path or '').rstrip('/')
            if request.method != 'GET' or path != '/daily_tasks':
                return resp
            if not _ui_enabled():
                return resp
            from flask_login import current_user
            from .access import user_allowed
            if not user_allowed(current_user):
                return resp
            ctype = resp.headers.get('Content-Type', '')
            if 'text/html' not in ctype or resp.status_code != 200 or resp.direct_passthrough:
                return resp
            body = resp.get_data(as_text=True)
            if 'method_week.js' in body or '</body>' not in body:
                return resp
            idx = body.rfind('</body>')
            body = body[:idx] + _SNIPPET + body[idx + len('</body>'):]
            resp.set_data(body)
        except Exception as exc:  # pragma: no cover
            logger.warning("method_week: ui inject failed: %s", exc)
        return resp
