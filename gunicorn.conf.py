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

WORKSHEETS_V1 (спринт «Конструктор листка»): тем же способом подключаем blueprint
`teacher_bp` (teacher/worksheets) и создаём его таблицы, если их ещё нет
(штатный паттерн AUTO-MIGRATION, как для parent_child_links / group_chats).
Отключение без деплоя кода: env WORKSHEETS_DISABLED=1.
Если строка `app.register_blueprint(teacher_bp)` появится в app.py — повторная
регистрация здесь пропускается.
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


def _register_section_stats(app):
    if os.environ.get('SECTION_STATS_DISABLED') == '1':
        _log.info('SECTION_STATS_V1: disabled by env')
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


def _register_teacher_worksheets(app):
    if os.environ.get('WORKSHEETS_DISABLED') == '1':
        _log.info('WORKSHEETS_V1: disabled by env')
        return
    if 'teacher' in getattr(app, 'blueprints', {}):
        return
    try:
        from teacher import teacher_bp
        app.register_blueprint(teacher_bp)
        _log.info('WORKSHEETS_V1: teacher_bp registered via gunicorn.conf.py')
    except Exception as e:  # никогда не роняем воркер из-за листков
        _log.warning('WORKSHEETS_V1: register failed: %r', e)
        return
    try:
        from models import db
        from teacher.worksheets.models import Worksheet, WorksheetTask, WorksheetAssignment
        with app.app_context():
            for model in (Worksheet, WorksheetTask, WorksheetAssignment):
                model.__table__.create(bind=db.engine, checkfirst=True)
        _log.info('WORKSHEETS_V1: tables ensured (worksheets, worksheet_tasks, worksheet_assignments)')
    except Exception as e:
        _log.warning('WORKSHEETS_V1: ensure tables failed: %r', e)


def post_worker_init(worker):
    """Вызывается после того, как воркер загрузил app:app, но до первого запроса."""
    app = _flask_app(worker)
    if app is None or not hasattr(app, 'register_blueprint'):
        _log.warning('gunicorn.conf.py: Flask app not found on worker, skip')
        return
    _register_section_stats(app)
    _register_teacher_worksheets(app)
