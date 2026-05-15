# -*- coding: utf-8 -*-
"""
Generator — генерация олимпиадной задачи.

Опция M (2026-05-14): гибрид моделей по уровням.
- level 1..HARD_LEVEL_THRESHOLD-1 -> deepseek-chat (быстрый, дешёвый, OK для l1-5)
- level >= HARD_LEVEL_THRESHOLD    -> claude-sonnet-4 (умеет арифметику для l6+)
Выбор делает pick_generator_model(level) из pipeline.config.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from pipeline.config import (
    GENERATOR_TEMPERATURE,
    GENERATOR_MAX_TOKENS,
    LEVEL_DESCRIPTIONS,
    SUBJECT_NAMES_RU,
    pick_generator_model,
)
from pipeline.openrouter_client import OpenRouterClient, TokenUsage
from pipeline.schemas import GeneratorOutput

logger = logging.getLogger("pipeline.generator")

# ─── Шкала уровней для промпта ────────────────────────────────────────────────
_LEVEL_SCALE_TEXT = "\n".join(
    f"  {k} — {v}" for k, v in LEVEL_DESCRIPTIONS.items()
)

# ─── Системный промпт ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""\
Ты — составитель задач для платформы FORMYLA (подготовка к матолимпиадам).

ШКАЛА УРОВНЕЙ (соблюдай СТРОГО):
{_LEVEL_SCALE_TEXT}

УТОЧНЕНИЯ ПО НИЗКИМ УРОВНЯМ:
- level=1: только прямая подстановка / один шаг. ЗАПРЕЩЕНЫ системы уравнений,
  квадратные уравнения, поиск всех решений, преобразование выражений.
- level=2: задача НЕ должна решаться чистой подстановкой формул без преобразований.
  Минимум 2 разных приёма (например: преобразование + проверка ОДЗ).
- level=3: обязателен этап анализа/отбора (ОДЗ, проверка корней, разбор случаев,
  отбрасывание посторонних значений). Не просто «решить уравнение».

ОБЩИЕ ТРЕБОВАНИЯ:
- Условие самодостаточное, без двусмысленностей
- Все обозначения определены, численные данные дают красивый ответ
- НЕ копируй известные олимпиадные задачи дословно
- level ≤ 3: ЗАПРЕЩЕНЫ параметры, исследование числа решений, доказательства неравенств
- level ≥ 4: ОБЯЗАТЕЛЬНА хотя бы одна нетривиальная идея

ПЕРЕД ВЫДАЧЕЙ JSON (для level ≥ 4 — ОБЯЗАТЕЛЬНО):
1. Подставь expected_answer_short обратно в условие и проверь, что равенство /
   условие задачи выполняется. Если ответ — перечисление, проверь КАЖДЫЙ элемент.
   Если ответ — пара/тройка чисел, подставь и убедись, что левая часть равна
   правой. Если уравнение не выполняется — ПЕРЕСЧИТАЙ и исправь ответ перед
   выдачей JSON. НЕ выдавай JSON, пока подстановка не подтверждает корректность.
2. Если answer_type = "пример+оценка" — проверь и пример (даёт ли он заявленное
   значение), и оценку (не противоречит ли).
3. Если answer_type = "доказательство" — приведи краткий контур доказательства
   в why_this_level, чтобы validator мог его проверить.

ФОРМАТ ВЫХОДА — КРИТИЧЕСКИ ВАЖНО:
Ответ должен быть ОДНИМ JSON-объектом и НИЧЕМ БОЛЬШЕ.
- НЕ пиши текст ДО JSON ("Проверяю задачу...", "Решение:", и т.п.).
- НЕ пиши текст ПОСЛЕ JSON.
- НЕ оборачивай в ```json ... ```.
- Первый символ ответа = открывающая фигурная скобка. Последний символ = закрывающая.

Если нужны вычисления-самопроверки, проведи их в УМЕ перед выдачей JSON,
а в JSON помести только итоговые поля.

Структура JSON:
{{
  "statement": "условие в LaTeX",
  "answer_type": "число|выражение|доказательство|пример+оценка|перечисление",
  "expected_answer_short": "...",
  "key_ideas": ["..."],
  "techniques": ["..."],
  "estimated_steps": N,
  "why_this_level": "...",
  "anti_pattern_check": "почему НЕ уровень N-1 и НЕ N+1"
}}
"""


def _build_user_prompt(
    subject: str,
    grade: int,
    level: int,
    topic_hint: Optional[str] = None,
    avoid_patterns: Optional[List[str]] = None,
    feedback: Optional[str] = None,
) -> str:
    """Формирует user-промпт для Generator."""
    subject_ru = SUBJECT_NAMES_RU.get(subject, subject)
    level_desc = LEVEL_DESCRIPTIONS.get(level, "")

    parts = [
        f"Предмет: {subject_ru}",
        f"Класс: {grade}",
        f"Уровень: {level} ({level_desc})",
    ]

    # Grade-aware послабления для младших классов
    if grade in (7, 8) and level >= 4:
        parts.append(
            "ВАЖНО: ученик " + str(grade) + " класса — это младший подросток. "
            "НЕ требуй настоящего муниципального/регионального уровня. "
            "Достаточно «школьник " + str(grade) + " класса с 1-2 простыми идеями». "
            "Используй только тот матаппарат, который школьник этого класса УЖЕ "
            "проходил (без логарифмов, тригонометрии, производных, "
            "комплексных чисел, теории сравнений)."
        )

    if topic_hint:
        parts.append(f"Подсказка по теме: {topic_hint}")

    if avoid_patterns:
        parts.append(f"Избегай паттернов: {', '.join(avoid_patterns)}")

    # M-2 (2026-05-14): усиленный self-check для l5 (deepseek-chat).
    # l6+ идут на claude-sonnet-4, ему такие напоминания не нужны.
    if level == 5:
        parts.append(
            "ВАЖНО ДЛЯ L5: дважды проверь арифметику ответа. "
            "Если в условии есть квадраты/кубы/степени — посчитай конкретно "
            "(например, 17^2 = 289) и подставь expected_answer_short обратно. "
            "Если левая часть не равна правой — пересчитай и исправь ДО выдачи JSON."
        )

    if feedback:
        parts.append(f"\n⚠️ ПРЕДЫДУЩАЯ ПОПЫТКА ОТКЛОНЕНА. Исправь:\n{feedback}")

    return "\n".join(parts)


async def generate_task(
    client: OpenRouterClient,
    subject: str,
    grade: int,
    level: int,
    topic_hint: Optional[str] = None,
    avoid_patterns: Optional[List[str]] = None,
    feedback: Optional[str] = None,
) -> tuple[GeneratorOutput, TokenUsage]:
    """
    Генерирует одну задачу.

    Returns:
        (GeneratorOutput, TokenUsage)

    Raises:
        OpenRouterError, ValidationError
    """
    user_msg = _build_user_prompt(
        subject, grade, level, topic_hint, avoid_patterns, feedback
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    # M-2 (2026-05-14): выбор модели по уровню — chat для l<6, claude для l>=6.
    model = pick_generator_model(level)
    data, usage = await client.chat_json(
        model=model,
        messages=messages,
        temperature=GENERATOR_TEMPERATURE,
        max_tokens=GENERATOR_MAX_TOKENS,
    )

    result = GeneratorOutput.model_validate(data)
    logger.info(
        "Generated task: model=%s, level=%d, type=%s, steps=%d",
        model, level, result.answer_type, result.estimated_steps,
    )
    return result, usage
