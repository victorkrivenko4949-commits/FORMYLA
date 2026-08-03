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
