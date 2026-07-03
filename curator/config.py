# -*- coding: utf-8 -*-
"""
config.py — Конфигурация модуля «Куратор».

Все пороговые значения, константы модели AI и настройки вынесены сюда,
чтобы не дублировать их в логике модулей.
"""

# ─── AI-модели ─────────────────────────────────────────────────────────────────
HINT_MODEL = "deepseek/deepseek-chat"
REVIEW_MODEL = "deepseek/deepseek-chat"
SUMMARY_MODEL = "deepseek/deepseek-chat"
ADVICE_MODEL = "deepseek/deepseek-chat"

# ─── Диагностика ───────────────────────────────────────────────────────────────
DIAG_TOPICS = ['algebra', 'geometry', 'combinatorics', 'number_theory', 'logic']

TOPIC_LABELS_RU = {
    'algebra': 'Алгебра',
    'geometry': 'Геометрия',
    'combinatorics': 'Комбинаторика',
    'number_theory': 'Теория чисел',
    'logic': 'Логика',
}

MIN_QUESTIONS_PER_TOPIC = 3
MAX_QUESTIONS_PER_TOPIC = 6
TOTAL_QUESTIONS_TARGET = 15
MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 8
START_DIFFICULTY = 4
CALIBRATION_QUESTIONS = 2

# ─── Планировщик ───────────────────────────────────────────────────────────────
MIN_PLAN_DAYS = 14
MAX_PLAN_DAYS = 365
DEFAULT_DAILY_TASKS = 5
DAYS_IN_WEEK = 7

# Веса для распределения тем по фазам
WEAK_TOPIC_WEIGHT = 0.5
MEDIUM_TOPIC_WEIGHT = 0.3
STRONG_TOPIC_WEIGHT = 0.2

# Пороги классификации тем (%)
STRONG_THRESHOLD = 70
WEAK_THRESHOLD = 40

# ─── Тьютор ─────────────────────────────────────────────────────────────────────
MAX_HINTS = 3

# ─── Прогресс ───────────────────────────────────────────────────────────────────
STUCK_DAYS_THRESHOLD = 3

# ─── Анализатор тем (Topic Analyzer) ────────────────────────────────────────────
# Пороги классификации тем для topic_analyzer
TOPIC_STRONG_THRESHOLD = 70.0      # СИЛЬНАЯ >= 70%
TOPIC_MEDIUM_THRESHOLD = 40.0      # 40% <= СРЕДНЯЯ < 70%
                                    # СЛАБАЯ < 40%
                                    # НЕТ ДАННЫХ — нет попыток

# Минимальное количество попыток для достоверной статистики
MIN_ATTEMPTS_FOR_ANALYSIS = 3

# ─── Олимпиадные советы ─────────────────────────────────────────────────────────
OLYMPIAD_MAX_RECOMMENDATIONS = 5

# ─── Банк задач (TaskBank) ──────────────────────────────────────────────────────
TASKBANK_DIFFICULTY_MIN = 1
TASKBANK_DIFFICULTY_MAX = 10
