# -*- coding: utf-8 -*-
"""
method_week — «Метод недели» (платная функция, ноябрь 2026).

Раз в неделю на странице задач дня ученик получает:
  1. разбор ОДНОГО метода (выбирает куратор по результатам ученика),
  2. три задачи на этот метод, сгенерированные deepseek-v4-pro
     (режим thinking), проверенные решателем и обработанные в LaTeX.
Проверка ответов — тот же пайплайн, что и в задачах дня
(services.solution_check_pipeline.check_solution).

Тестовый период: видно только аккаунтам из METHOD_WEEK_ALLOWED_USERS
(по умолчанию lavrik,victor) — см. access.py.

Подключение без правки app.py: ``attach(daily_tasks_bp)`` вешает
callback на регистрацию блюпринта задач дня и в этот момент
регистрирует method_week_bp, paywall и инжектор UI-скрипта.
"""
from __future__ import annotations

import logging

from flask import Blueprint

logger = logging.getLogger(__name__)

method_week_bp = Blueprint('method_week', __name__, url_prefix='/method_week')

from . import routes  # noqa: E402, F401

_INSTALLED = False


def _install(app) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    try:
        app.register_blueprint(method_week_bp)
    except Exception as exc:  # pragma: no cover
        logger.error("method_week: register_blueprint failed: %s", exc)
    try:
        from .paywall import install_paywall
        install_paywall(app)
    except Exception as exc:  # pragma: no cover
        logger.error("method_week: paywall install failed: %s", exc)
    try:
        from .ui_inject import install_ui_injector
        install_ui_injector(app)
    except Exception as exc:  # pragma: no cover
        logger.error("method_week: ui injector install failed: %s", exc)


def attach(host_bp) -> None:
    """Вызывается из daily_tasks/__init__.py. Никогда не бросает."""
    try:
        host_bp.record_once(lambda state: _install(state.app))
    except Exception as exc:  # pragma: no cover
        logger.error("method_week: attach failed: %s", exc)
