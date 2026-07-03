# -*- coding: utf-8 -*-
"""
curator — Пакет «Куратор» (AI-наставник).

Модули:
  diagnostics  — входное тестирование (диагностика)
  planner      — построение учебного плана (roadmap)
  tutor        — помощь с задачами (подсказки, проверка)
  progress     — отслеживание прогресса и мотивация
  task_bank    — банк задач для диагностики, планов и тьютора
  config       — конфигурация и пороговые значения
"""

from flask import Blueprint

curator_bp = Blueprint(
    'curator',
    __name__,
    url_prefix='/curator',
    template_folder='../templates/curator',
    static_folder='../static',
)

from . import routes       # noqa: E402, F401
from . import diagnostics  # noqa: E402, F401
from . import planner      # noqa: E402, F401
from . import tutor        # noqa: E402, F401
from . import progress     # noqa: E402, F401
from . import task_bank    # noqa: E402, F401
from . import config       # noqa: E402, F401
