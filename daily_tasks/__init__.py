# -*- coding: utf-8 -*-
"""
daily_tasks — Пакет «Задачи дня» (Daily Tasks).

Генерирует 10 персонализированных задач через мульти-LLM пайплайн:
  Gemini 3.1 Pro (план) -> Opus 4.7 (генерация) -> GPT-5.5 (аудит) -> Opus 4.7 (фикс).
"""

from flask import Blueprint

daily_tasks_bp = Blueprint(
    'daily_tasks',
    __name__,
    url_prefix='/daily_tasks',
    template_folder='../templates/daily_tasks',
    static_folder='../static',
)

from . import routes  # noqa: E402, F401

from .intake_probe import attach as _intake_probe_attach
_intake_probe_attach(daily_tasks_bp)

# «Метод недели» + план куратора + paywall. Подключается в момент
# регистрации daily_tasks_bp в app.py — без правки app.py. Любая ошибка здесь
# не ломает задачи дня. Блоки на странице задач дня временно скрыты для всех
# (method_week/ui_inject.py, вернуть: METHOD_WEEK_UI_ENABLED=1), API работает;
# paywall ВКЛЮЧЁН по умолчанию с 28.10.2026 (PAYWALL_ENABLED=0 — выключить).
try:  # pragma: no cover
    from method_week import attach as _method_week_attach
    _method_week_attach(daily_tasks_bp)
except Exception as _mw_exc:  # noqa: F841
    import logging as _logging
    _logging.getLogger(__name__).error("method_week attach failed: %s", _mw_exc)

# Админ-API «задачи дня ученика» (find_user + user/<id>). Как и method_week,
# вешается на daily_tasks_bp без правки app.py; ошибка не ломает задачи дня.
try:  # pragma: no cover
    from .admin_api import attach as _admin_api_attach
    _admin_api_attach(daily_tasks_bp)
except Exception as _aa_exc:  # noqa: F841
    import logging as _logging
    _logging.getLogger(__name__).error("daily_tasks admin_api attach failed: %s", _aa_exc)

# Баг Лаврика #23: текст решения/ответа в модалке задач дня не теряется при
# перерисовке, поле надёжно фокусируется. Скрипт вставляется after_request-хуком
# без правки шаблона. Отключить: DT_SOLUTION_GUARD_DISABLED=1.
try:  # pragma: no cover
    from .solution_guard import attach as _solution_guard_attach
    _solution_guard_attach(daily_tasks_bp)
except Exception as _sg_exc:  # noqa: F841
    import logging as _logging
    _logging.getLogger(__name__).error("daily_tasks solution_guard attach failed: %s", _sg_exc)

# TG_FIX_V2: встроенный браузер Telegram (Android/iOS) кэширует HTML
# /daily_tasks и после деплоя показывает старую страницу (старое окно задачи,
# старые кнопки). Запрещаем кэширование HTML этой страницы — статику бьёт
# asset_version, динамический HTML теперь всегда свежий.
from flask import request as _dt_request


@daily_tasks_bp.after_request
def _dt_no_store_html(resp):
    try:
        if _dt_request.method == 'GET' and (_dt_request.path or '').rstrip('/') == '/daily_tasks':
            if 'text/html' in resp.headers.get('Content-Type', ''):
                resp.headers['Cache-Control'] = 'no-store, must-revalidate'
                resp.headers['Pragma'] = 'no-cache'
                resp.headers['Expires'] = '0'
    except Exception:  # pragma: no cover
        pass
    return resp

# Минимум 15 символов текстового решения для задач уровня 2+ (2, 3, 4), если нет
# фото. Серверная проверка (before_request на /submit и /submit_ai) + клиентский
# скрипт static/js/dt_solution_minlen.js (вставляется after_request-хуком).
# Отключить: DT_SOLUTION_MINLEN_DISABLED=1. Порог: DT_SOLUTION_MIN_LEN (15),
# уровень: DT_SOLUTION_MIN_LEVEL (2).
try:  # pragma: no cover
    from .solution_minlen import attach as _solution_minlen_attach
    _solution_minlen_attach(daily_tasks_bp)
except Exception as _sm_exc:  # noqa: F841
    import logging as _logging
    _logging.getLogger(__name__).error("daily_tasks solution_minlen attach failed: %s", _sm_exc)
