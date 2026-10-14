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

# «Метод недели» + план куратора + paywall (ноябрь 2026). Подключается в момент
# регистрации daily_tasks_bp в app.py — без правки app.py. Любая ошибка здесь
# не ломает задачи дня. Тестовый период: видно только lavrik и victor
# (METHOD_WEEK_ALLOWED_USERS), paywall выключен (PAYWALL_ENABLED=0).
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
