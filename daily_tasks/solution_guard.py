# -*- coding: utf-8 -*-
"""
Баг Лаврика #23 — подключение static/js/dt_solution_guard.js к странице /daily_tasks
без правки шаблона daily_tasks_dashboard.html и app.py.

Как method_week / admin_api: вешается на daily_tasks_bp через attach(bp).
after_request для HTML-ответов 200 блюпринта, в которых есть dt-init-data
(т.е. именно дашборд задач дня), добавляет <script defer> перед </body>.

Отключить без деплоя: DT_SOLUTION_GUARD_DISABLED=1.
Любая ошибка логируется и не ломает страницу — ответ уходит как есть.
"""
import logging
import os
import time

log = logging.getLogger(__name__)

_SCRIPT_SRC = '/static/js/dt_solution_guard.js'
_MARKER = 'dt-init-data'
_VERSION = str(int(time.time()))  # меняется на каждом старте процесса → сброс кэша после деплоя


def _disabled() -> bool:
    return os.environ.get('DT_SOLUTION_GUARD_DISABLED', '0').strip().lower() in ('1', 'true', 'yes')


def _inject(response):
    try:
        if _disabled():
            return response
        if response.status_code != 200:
            return response
        if getattr(response, 'direct_passthrough', False):
            return response
        ctype = response.headers.get('Content-Type', '') or ''
        if 'text/html' not in ctype:
            return response
        body = response.get_data(as_text=True)
        if not body or _MARKER not in body or _SCRIPT_SRC in body:
            return response
        tag = '<script src="%s?v=%s" defer></script>\n' % (_SCRIPT_SRC, _VERSION)
        idx = body.rfind('</body>')
        if idx == -1:
            body = body + tag
        else:
            body = body[:idx] + tag + body[idx:]
        response.set_data(body)
    except Exception as exc:  # pragma: no cover
        log.warning('dt_solution_guard inject failed: %s', exc)
    return response


def attach(bp):
    """Повесить after_request на daily_tasks_bp (до регистрации в app)."""
    bp.after_request(_inject)
    log.info('DT_SOLUTION_GUARD: attached to %s', getattr(bp, 'name', bp))
