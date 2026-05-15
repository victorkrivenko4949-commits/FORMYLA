# -*- coding: utf-8 -*-
"""
Конфигурация пайплайна генерации задач для Адаптивного теста.

Все модели и параметры вынесены сюда для удобной замены.
"""
import os

# ─── OpenRouter ────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "https://formyla.ru")
OPENROUTER_APP_NAME = "FORMYLA-AdaptivePipeline"

# ─── Модели (Опция M, 2026-05-14): гибрид Generator по уровням ───────────────
# Тест после H-2 показал: новый Validator корректно ловит реальные арифметические
# ошибки deepseek-chat на l6 (2²+45²=2029, не 2024; ОДЗ в иррац. неравенствах;
# key_ideas-лозунги вместо доказательства). R1 умеет считать, но 5-7 мин/вызов.
# Решение: для level >= HARD_LEVEL_THRESHOLD используем claude-sonnet-4 как
# Generator (быстрый, умеет арифметику, ~$0.05/вызов).
#
# Self-bias Generator=Validator при level>=6 не страшен: Validator проверяет
# подстановкой ответа в условие (математика, не доверие модели), и промпты
# Generator (создатель) и Validator (критик) противоположны по роли.
GENERATOR_MODEL_DEFAULT = os.getenv("ADAPTIVE_GENERATOR_MODEL", "deepseek/deepseek-chat")
GENERATOR_MODEL_HARD = os.getenv("ADAPTIVE_GENERATOR_MODEL_HARD", "anthropic/claude-sonnet-4")
HARD_LEVEL_THRESHOLD = int(os.getenv("ADAPTIVE_HARD_LEVEL_THRESHOLD", "6"))
GENERATOR_TEMPERATURE = 0.8
GENERATOR_MAX_TOKENS = 4096
# Backward-compat: код, использующий GENERATOR_MODEL напрямую, получит default.
GENERATOR_MODEL = GENERATOR_MODEL_DEFAULT


def pick_generator_model(level: int) -> str:
    """Выбор модели Generator по уровню сложности (Опция M)."""
    if level >= HARD_LEVEL_THRESHOLD:
        return GENERATOR_MODEL_HARD
    return GENERATOR_MODEL_DEFAULT

VALIDATOR_MODEL = os.getenv("ADAPTIVE_VALIDATOR_MODEL", "anthropic/claude-sonnet-4")
VALIDATOR_TEMPERATURE = 0.1
VALIDATOR_MAX_TOKENS = 3000

# F-4 (2026-05-14): Calibrator переведён с openai/gpt-4o на claude-sonnet-4.
# Причина: 58 ошибок 403 от gpt-4o на RU-IP в свежем логе.
# Validator и Calibrator имеют РАЗНЫЕ роли — корректность vs уровень.
CALIBRATOR_MODEL = os.getenv("ADAPTIVE_CALIBRATOR_MODEL", "anthropic/claude-sonnet-4")
CALIBRATOR_TEMPERATURE = 0.2
CALIBRATOR_MAX_TOKENS = 3000

# H-3 (2026-05-14): возврат порога уверенности Calibrator с 0.6 на 0.7.
# F-2 снижал до 0.6 как компенсацию за строгий Validator; после H-2
# (новая роль Validator) ослабление Calibrator больше не нужно — задачи,
# проходящие Validator корректны, и Calibrator должен подтверждать уровень
# с разумной уверенностью.
CALIBRATOR_CONFIDENCE_MIN = float(os.getenv("ADAPTIVE_CALIBRATOR_CONF_MIN", "0.7"))

# ─── Управляющий цикл ─────────────────────────────────────────────────────────
MAX_ITERATIONS = int(os.getenv("ADAPTIVE_MAX_ITER", "4"))
MAX_COST_USD_DEFAULT = float(os.getenv("ADAPTIVE_MAX_COST_USD", "5.0"))

# ─── Skip-list ячеек ──────────────────────────────────────────────────────────
# F-1 (2026-05-14): SKIP_CELLS теперь хранит тройки (subject, grade, level).
# Старые пары (grade, level) автоматически расширяются на ВСЕ предметы через
# helper is_skipped_cell(...) ниже.
#
# Тонкая настройка после диагностики full_regen_20260514_142938.log:
#   algebra/g7/l6, algebra/g7/l7, algebra/g8/l7 — Generator не справляется
#   с олимпиадной алгеброй на этих возрастах, валит почти всё.
#   algebra/g9/l6, algebra/g9/l7 — 100% review (математически неверные ответы).
#
# Универсальные «бессмысленные» комбинации остаются для всех предметов:
#   (7,7), (8,7) — закл. этап для 7-8 классов почти не существует
#   (7,6)        — закл. этап для 7 класса почти не существует
#   (13,1), (13,2) — выпускники, тривиальный уровень не нужен
SKIP_CELLS_GENERIC = {
    (7, 7), (8, 7), (7, 6),
    (13, 1), (13, 2),
}
SKIP_CELLS_SUBJECT = {
    ("algebra", 7, 6), ("algebra", 7, 7),
    ("algebra", 8, 7),
    ("algebra", 9, 6), ("algebra", 9, 7),
}


def is_skipped_cell(subject: str, grade: int, level: int) -> bool:
    if (grade, level) in SKIP_CELLS_GENERIC:
        return True
    if (subject, grade, level) in SKIP_CELLS_SUBJECT:
        return True
    return False


# Backward-compat: старый код может импортировать SKIP_CELLS как set пар.
# Оставляем, но новый код должен использовать is_skipped_cell().
SKIP_CELLS = SKIP_CELLS_GENERIC

# ─── Retry / Rate-limit ───────────────────────────────────────────────────────
# F-6 (2026-05-14): RETRY_WAIT_MAX 30 -> 90 для устойчивости к 429-флапу.
RETRY_ATTEMPTS = 3
RETRY_WAIT_MIN = 2
RETRY_WAIT_MAX = 90

# ─── Дедупликация ─────────────────────────────────────────────────────────────
DEDUP_COSINE_THRESHOLD = 0.92
EMBEDDING_MODEL = os.getenv("ADAPTIVE_EMBEDDING_MODEL", "openai/text-embedding-3-small")

# ─── Стоимость моделей ($/1M tokens) — для cost_log ───────────────────────────
MODEL_COSTS = {
    "deepseek/deepseek-chat":    {"input": 0.14,  "output": 0.28},
    "deepseek/deepseek-r1":      {"input": 0.55,  "output": 2.19},
    "anthropic/claude-sonnet-4": {"input": 3.00,  "output": 15.00},
    "openai/gpt-4o":             {"input": 2.50,  "output": 10.00},
    "openai/text-embedding-3-small": {"input": 0.02, "output": 0.0},
}

# ─── Шкала уровней (канон) ────────────────────────────────────────────────────
LEVEL_DESCRIPTIONS = {
    1: "Чуть выше учебника, 1-2 шага, без приёмов",
    2: "Школьный ВсОШ, 2-3 шага, привычные приёмы",
    3: "Школьный/нач. муниципального, 3-4 шага, аккуратность",
    4: "Муниципальный, ОДНА нетривиальная идея",
    5: "Сложн. муниц./лёгкий региональный, ДВЕ идеи, анализ случаев",
    6: "Региональный, 2-3 связанные идеи, оценка+пример",
    7: "Сложн. региональный/закл. этап, творческое решение",
}

# ─── Предметы ─────────────────────────────────────────────────────────────────
SUBJECTS = [
    "algebra", "geometry", "number_theory",
    "combinatorics", "logic", "set_theory",
]

SUBJECT_NAMES_RU = {
    "algebra": "Алгебра",
    "geometry": "Геометрия",
    "number_theory": "Теория чисел",
    "combinatorics": "Комбинаторика",
    "logic": "Логика",
    "set_theory": "Теория множеств",
    "probability": "Теория вероятностей",
}
