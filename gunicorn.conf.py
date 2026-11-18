# -*- coding: utf-8 -*-
"""gunicorn.conf.py — gunicorn читает этот файл автоматически из текущей папки
(корень репо на Render: `gunicorn app:app ...`). Флаги командной строки из
стартовой команды имеют приоритет над этим файлом — здесь только хуки.

SECTION_STATS_V1: подключаем статистику по разделам / точный таймер / опрос
«102 метода» / «Мои чертежи» к уже загруженному Flask-приложению, не правя app.py.
Отключение без деплоя кода: env SECTION_STATS_DISABLED=1.

USER_RETURNS_V1: блок «Возвращения» (сколько людей пришли 2-й, 3-й, 4-й… раз;
визит = серия действий с паузами ≤ 60 мин) сверху /admin/users и страница
/admin/users/returns. Отключение: env USER_RETURNS_DISABLED=1.

USER_LAST_SEEN_V1 (18.10.2026): блок «Последний заход — когда каждый был в последний
раз» на /admin/users (Jinja-глобал user_last_seen_block) и страница /admin/users/last_seen.
Живёт в том же services/user_returns.py и выключается тем же USER_RETURNS_DISABLED=1.

METHODS_AUTH_GATE_V1 (15.11.2026): раздел «102 метода» (/olympiads/methods/* и
/static/methods/*) открыт только зарегистрированным; анонимов и гостей перекидывает
на /register. Логика — в services/methods_auth_gate.py.
Отключение без деплоя кода: env METHODS_GATE_DISABLED=1.

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


def _register_user_returns(app):
    if os.environ.get('USER_RETURNS_DISABLED') == '1':
        _log.info('USER_RETURNS_V1: disabled by env')
        return
    if getattr(app, '_user_returns_registered', False) or 'user_returns' in getattr(app, 'blueprints', {}):
        return
    try:
        from services.user_returns import register, returns_distribution, last_seen_table
        register(app)

        def _user_returns_block(gap_min=60, days=0):
            """Jinja-глобал для templates/admin/users_stats.html. Никогда не роняет страницу."""
            try:
                return returns_distribution(gap_min=gap_min, days=days)
            except Exception as _e:
                try:
                    from models import db
                    db.session.rollback()
                except Exception:
                    pass
                _log.warning('USER_RETURNS_V1: block failed: %r', _e)
                return None

        def _user_last_seen_block(gap_min=60):
            """USER_LAST_SEEN_V1: Jinja-глобал «когда каждый заходил в последний раз». Никогда не роняет страницу."""
            try:
                return last_seen_table(gap_min=gap_min)
            except Exception as _e:
                try:
                    from models import db
                    db.session.rollback()
                except Exception:
                    pass
                _log.warning('USER_LAST_SEEN_V1: block failed: %r', _e)
                return None

        app.jinja_env.globals['user_returns_block'] = _user_returns_block
        app.jinja_env.globals['user_last_seen_block'] = _user_last_seen_block
        _log.info('USER_RETURNS_V1 + USER_LAST_SEEN_V1: registered via gunicorn.conf.py')
    except Exception as e:  # никогда не роняем воркер из-за статистики
        _log.warning('USER_RETURNS_V1: register failed: %r', e)


def _register_methods_gate(app):
    if os.environ.get('METHODS_GATE_DISABLED') == '1':
        _log.info('METHODS_AUTH_GATE_V1: disabled by env')
        return
    if getattr(app, '_methods_auth_gate_registered', False):
        return
    try:
        from services.methods_auth_gate import register
        register(app)
        _log.info('METHODS_AUTH_GATE_V1: registered via gunicorn.conf.py')
    except Exception as e:  # никогда не роняем воркер из-за гейта
        _log.warning('METHODS_AUTH_GATE_V1: register failed: %r', e)


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
        from teacher.worksheets.models import Worksheet, WorksheetTask, WorksheetAssignment, WorksheetDailyItem
        with app.app_context():
            for model in (Worksheet, WorksheetTask, WorksheetAssignment, WorksheetDailyItem):
                model.__table__.create(bind=db.engine, checkfirst=True)
        _log.info('WORKSHEETS_V1: tables ensured (worksheets, worksheet_tasks, worksheet_assignments, worksheet_daily_items)')
    except Exception as e:
        _log.warning('WORKSHEETS_V1: ensure tables failed: %r', e)


def post_worker_init(worker):
    """Вызывается после того, как воркер загрузил app:app, но до первого запроса."""
    app = _flask_app(worker)
    if app is None or not hasattr(app, 'register_blueprint'):
        _log.warning('gunicorn.conf.py: Flask app not found on worker, skip hooks')
        return
    _register_methods_gate(app)
    _register_section_stats(app)
    _register_user_returns(app)
    _register_teacher_worksheets(app)
