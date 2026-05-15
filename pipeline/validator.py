# -*- coding: utf-8 -*-
"""
Validator — проверка корректности задачи через anthropic/claude-sonnet-4.

НЕ решает задачу полностью — проверяет корректность, однозначность,
полноту данных, соответствие классу и LaTeX.
"""
from __future__ import annotations

import logging
from typing import Dict

from pipeline.config import (
    VALIDATOR_MODEL,
    VALIDATOR_TEMPERATURE,
    VALIDATOR_MAX_TOKENS,
    LEVEL_DESCRIPTIONS,
    SUBJECT_NAMES_RU,
)
from pipeline.openrouter_client import OpenRouterClient, TokenUsage
from pipeline.schemas import GeneratorOutput, ValidatorOutput

logger = logging.getLogger("pipeline.validator")

SYSTEM_PROMPT = """\
Ты — рецензент-математик. Твоя задача: проверить МАТЕМАТИЧЕСКУЮ КОРРЕКТНОСТЬ
задачи (условие + ответ), а НЕ строгость решения.

ВАЖНО про key_ideas:
key_ideas — это НАБРОСОК идей решения, черновик от автора задачи. Это НЕ
формальное доказательство и НЕ полное решение. Допустимы пропуски шагов,
нестрогие переходы, отсутствие проверки границ. Не суди key_ideas как
экзаменационную работу.

ИСКЛЮЧЕНИЕ: если answer_type == "доказательство", тогда key_ideas — это и
есть решение, и проверять его нужно СТРОГО как доказательство (логические
пробелы → blocker).

═══════════════════════════════════════════════════════════════════════════
ЧЕКЛИСТ (выполняй по порядку):

1) УСЛОВИЕ ОДНОЗНАЧНО (обязательно)
   - Постановка задачи понятна, нет противоречий, не хватает данных?
   - Если ДА есть противоречие/неоднозначность критическая → blocker.

2) ОТВЕТ КОРРЕКТЕН (обязательно — это ловит арифметические ошибки Generator)
   - Возьми expected_answer_short и ПОДСТАВЬ в условие — выполняется ли?
   - Если answer_type == "число" / "выражение" / "множество чисел":
     * проверь арифметику подстановкой (например, 6² + 17² = 36 + 289 = 325, а не 365)
     * проверь, что ответ единственный (если задача требует единственности)
   - Если ответ НЕВЕРЕН → blocker (это главная проверка!).

3) LATEX И ТИПОГРАФИКА
   - Все формулы валидны, скобки сбалансированы, нет $...$ внутри $$...$$ и т.п.
   - Лёгкая ошибка LaTeX → major. FAIL только если 2+ серьёзных ломающих ошибки.

4) СООТВЕТСТВИЕ КЛАССУ
   - Задача требует материала, недоступного классу?
   - Используются понятия на 2+ класса выше → major.
   - Сильно проще заявленного уровня → major.
   - FAIL только если 2+ major по этому пункту.

5) KEY_IDEAS (только непротиворечивость, НЕ строгость)
   - Идеи НЕ ПРОТИВОРЕЧАТ правильному ответу?
   - Если идеи приходят к ОТЛИЧНОМУ от expected_answer_short результату → blocker.
   - Нестрогие/пропущенные шаги, отсутствие границ, "очевидно" — это minor,
     НИКОГДА не FAIL (кроме answer_type == "доказательство").

═══════════════════════════════════════════════════════════════════════════
SEVERITY:

BLOCKER (→ FAIL):
- Неверный ответ (подстановка не даёт expected_answer_short).
- Противоречие в условии / задача нерешаема / неоднозначность критическая.
- key_ideas приходит к ДРУГОМУ ответу, чем expected_answer_short.
- Для answer_type == "доказательство": логические пробелы в key_ideas.

MAJOR (FAIL только если набралось 2+ MAJOR одного типа):
- Ошибка LaTeX, не ломающая полностью смысл.
- Несоответствие класса (понятия на 2 класса выше).
- Задача сильно проще/сложнее заявленного уровня.

MINOR (НИКОГДА не FAIL):
- Стилистика, форматирование, пропуски шагов в key_ideas (если answer_type ≠
  доказательство), нестрогие переходы, отсутствие проверки границ.

═══════════════════════════════════════════════════════════════════════════
ПРАВИЛО ВЕРДИКТА:
- Есть хотя бы 1 BLOCKER → FAIL.
- Нет blocker, есть 2+ MAJOR одного типа → FAIL.
- Иначе → PASS (даже если есть minor / 1 major).

ВЫХОД — строго JSON (без markdown-обёртки):
{
  "verdict": "PASS" или "FAIL",
  "issues": [{"type": "...", "description": "...", "severity": "blocker|major|minor"}],
  "fix_hint": "подсказка для исправления (если FAIL)"
}
"""


def _build_user_prompt(
    task: GeneratorOutput,
    subject: str,
    grade: int,
    level: int,
) -> str:
    """Формирует user-промпт для Validator."""
    subject_ru = SUBJECT_NAMES_RU.get(subject, subject)
    level_desc = LEVEL_DESCRIPTIONS.get(level, "")

    task_json = task.model_dump_json(indent=2, ensure_ascii=False)

    return (
        f"Предмет: {subject_ru}\n"
        f"Класс: {grade}\n"
        f"Заявленный уровень: {level} ({level_desc})\n\n"
        f"JSON задачи от Generator:\n{task_json}"
    )


async def validate_task(
    client: OpenRouterClient,
    task: GeneratorOutput,
    subject: str,
    grade: int,
    level: int,
) -> tuple[ValidatorOutput, TokenUsage]:
    """
    Проверяет задачу на корректность.

    Returns:
        (ValidatorOutput, TokenUsage)
    """
    user_msg = _build_user_prompt(task, subject, grade, level)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    data, usage = await client.chat_json(
        model=VALIDATOR_MODEL,
        messages=messages,
        temperature=VALIDATOR_TEMPERATURE,
        max_tokens=VALIDATOR_MAX_TOKENS,
    )

    result = ValidatorOutput.model_validate(data)

    # H-2 (2026-05-14): постпроцессинг согласован с новым system prompt.
    # Правило вердикта:
    #   - 1+ BLOCKER -> FAIL.
    #   - 0 blockers и 2+ MAJOR одного типа -> FAIL.
    #   - Иначе -> PASS (даже 1 major / много minor допустимы).
    blockers = [i for i in result.issues if i.severity == "blocker"]
    majors = [i for i in result.issues if i.severity == "major"]

    # Снимаем major-флаги "натуральные/различные/область" для answer_type=число
    if task.answer_type == "число":
        suspicious_kws = (
            "натуральн", "различн", "облас", "одз", "целых",
            "положительн", "указано множество",
        )
        before = len(majors)
        majors = [
            m for m in majors
            if not any(kw in (m.description or "").lower() for kw in suspicious_kws)
        ]
        if len(majors) < before:
            logger.info(
                "Cleared %d majors про 'натуральные/различные' для answer_type=число",
                before - len(majors),
            )

    # Подсчёт MAJOR одного типа (для правила 2+ -> FAIL).
    from collections import Counter
    major_type_counts = Counter((m.type or "").lower() for m in majors)
    repeated_major_types = [t for t, c in major_type_counts.items() if c >= 2]

    should_fail = bool(blockers) or bool(repeated_major_types)

    if should_fail and result.verdict == "PASS":
        logger.warning(
            "Overriding PASS->FAIL: blockers=%d, repeated_major_types=%s",
            len(blockers), repeated_major_types,
        )
        result.verdict = "FAIL"
    elif not should_fail and result.verdict == "FAIL":
        logger.info(
            "Overriding FAIL->PASS: no blockers, no 2+ majors of same type "
            "(majors=%d, types=%s)",
            len(majors), list(major_type_counts.keys()),
        )
        result.verdict = "PASS"
        result.fix_hint = ""

    logger.info(
        "Validation: verdict=%s, issues=%d (blockers=%d, majors=%d, repeated_types=%s)",
        result.verdict, len(result.issues),
        len(blockers), len(majors), repeated_major_types,
    )
    return result, usage
