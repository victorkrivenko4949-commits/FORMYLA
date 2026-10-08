# -*- coding: utf-8 -*-
"""gunicorn.conf.py — gunicorn читает этот файл автоматически из текущей папки
(корень репо на Render: `gunicorn app:app ...`). Флаги командной строки из
стартовой команды имеют приоритет над этим файлом — здесь только хуки.

SECTION_STATS_V1: подключаем статистику по разделам / точный таймер / опрос
«102 метода» / «Мои чертежи» к уже загруженному Flask-приложению, не правя app.py.
Отключение без деплоя кода: env SECTION_STATS_DISABLED=1.

Если когда-нибудь строка
    from services.site_stats import register as _register_site_stats; _register_site_stats(app)
появится в app.py — повторный вызов здесь безопасен (есть защита от двойной регистрации).
"""
import os
import logging

_log = logging.getLogger('gunicorn.error')


def _flask_app(worker):
    app = getattr(worker, 'wsgi', None)
    if app is None:
        try:
            app = worker.app.callable
        except Exception:
            app = None
    if app is None:
        try:
            app = worker.app.wsgi()
        except Exception:
            app = None
    return app


def post_worker_init(worker):
    """Вызывается после того, как воркер загрузил app:app, но до первого запроса."""
    if os.environ.get('SECTION_STATS_DISABLED') == '1':
        _log.info('SECTION_STATS_V1: disabled by env')
        return
    app = _flask_app(worker)
    if app is None or not hasattr(app, 'register_blueprint'):
        _log.warning('SECTION_STATS_V1: Flask app not found on worker, skip')
        return
    if getattr(app, '_section_stats_registered', False) or 'site_stats' in getattr(app, 'blueprints', {}):
        return
    try:
        from services.site_stats import register
        register(app)
        app._section_stats_registered = True
        _log.info('SECTION_STATS_V1: registered via gunicorn.conf.py')
    except Exception as e:  # никогда не роняем воркер из-за статистики
        _log.warning('SECTION_STATS_V1: register failed: %r', e)
