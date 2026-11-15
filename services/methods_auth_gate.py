# -*- coding: utf-8 -*-
"""METHODS_AUTH_GATE_V1 (15.11.2026) — раздел «102 метода» только для зарегистрированных.

Аноним или гостевой аккаунт (is_guest) при заходе в раздел получает редирект
на страницу регистрации /register?next=<куда шёл>. Закрыты:
  • /olympiads/methods            — страница-обёртка с атласом;
  • /olympiads/methods/atlas.html — сам атлас (iframe);
  • /olympiads/methods/<код>, /olympiads/methods/section/…, /olympiads/methods/task/…;
  • /static/methods/…             — прямые ссылки на файл атласа в обход раздела.

Подключение — из gunicorn.conf.py (post_worker_init), app.py и routes/olympiad.py
не правятся. Отключение без деплоя кода: env METHODS_GATE_DISABLED=1.
"""
import os
import logging
from urllib.parse import quote

from flask import request, redirect, jsonify

_log = logging.getLogger(__name__)

REGISTER_URL = '/register'
METHODS_URL = '/olympiads/methods'
_PREFIXES = ('/olympiads/methods', '/static/methods')


def _is_methods_path(path):
    path = (path or '').rstrip('/')
    for prefix in _PREFIXES:
        if path == prefix or path.startswith(prefix + '/'):
            return True
    return False


def _is_registered_user():
    """Настоящий (не гостевой) залогиненный пользователь. При любой ошибке — False."""
    try:
        from flask_login import current_user
        return bool(current_user.is_authenticated
                    and not getattr(current_user, 'is_guest', False))
    except Exception:
        return False


def _next_url():
    """Куда вернуть после регистрации: файл атласа всегда меняем на страницу раздела."""
    path = request.path or METHODS_URL
    if path.startswith('/static/methods') or path.endswith('/atlas.html'):
        return METHODS_URL
    return path


def _methods_auth_gate():
    if not _is_methods_path(request.path):
        return None
    if _is_registered_user():
        return None
    if (request.method not in ('GET', 'HEAD')
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'):
        return jsonify(error='Зарегистрируйтесь, чтобы открыть раздел «102 метода».',
                       register_url=REGISTER_URL), 401
    return redirect(REGISTER_URL + '?next=' + quote(_next_url(), safe='/'))


def register(app):
    """Повесить гейт на приложение. Повторный вызов безопасен."""
    if os.environ.get('METHODS_GATE_DISABLED') == '1':
        _log.info('METHODS_AUTH_GATE_V1: disabled by env')
        return False
    if getattr(app, '_methods_auth_gate_registered', False):
        return True
    app.before_request(_methods_auth_gate)
    app._methods_auth_gate_registered = True
    return True
