# -*- coding: utf-8 -*-
"""
Polisher service: final formatting pass.
Fixes LaTeX, improves wording, ensures consistency.
CRITICAL: Does NOT change mathematical content.
"""
import json
import logging

from services.openrouter_client import openrouter

logger = logging.getLogger(__name__)

MODEL = "openai/gpt-4o"
TEMPERATURE = 0.2

SYSTEM_MSG = """Ты — редактор-корректор олимпиадных задач. Твоя задача — финальная полировка текста: исправить LaTeX, улучшить формулировки, убрать лишнее. НЕ менять математическое содержание."""


def polish_problem(problem: dict) -> dict:
    """
    Polish a problem: fix LaTeX, improve wording.

    Args:
        problem: dict with statement, solution, answer

    Returns: dict with polished statement, solution, answer, changes_made
    Fallback: returns original if model says no_change needed.
    """
    statement = problem.get('statement', '')
    solution = problem.get('solution', '')
    answer = problem.get('answer', '')

    prompt = _build_prompt(statement, solution, answer)

    result = openrouter.chat(
        model=MODEL,
        messages=[
            dict(role="system", content=SYSTEM_MSG),
            dict(role="user", content=prompt)
        ],
        temperature=TEMPERATURE,
        max_tokens=4096,
    )

    content = result["content"]
    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        data = json.loads(content.strip())
    except json.JSONDecodeError:
        logger.error(f"[Polisher] JSON parse error: {content[:200]}")
        # Fallback: return original
        return dict(
            statement=statement,
            solution=solution,
            answer=answer,
            changes_made=[],
            _error='JSON parse failed',
            _usage=result['usage'],
            _cost=result['cost_usd'],
        )

    # Handle no_change response
    if data.get('status') == 'no_change':
        logger.info(f"[Polisher] No changes needed: {data.get('reason', '')}")
        return dict(
            statement=statement,
            solution=solution,
            answer=answer,
            changes_made=[],
            _usage=result['usage'],
            _cost=result['cost_usd'],
        )

    # Validate polished output has required fields
    for field in ['statement', 'solution', 'answer']:
        if not data.get(field):
            data[field] = problem.get(field, '')

    data['_usage'] = result['usage']
    data['_cost'] = result['cost_usd']

    openrouter.log_cost_to_db('polish', MODEL, result['usage'], result['cost_usd'])
    changes = data.get('changes_made', [])
    logger.info(f"[Polisher] {len(changes)} changes made, ${result['cost_usd']:.4f}")
    return data


def _build_prompt(statement: str, solution: str, answer: str) -> str:
    """Build the polisher prompt with all rules."""
    no_change_json = '{"status": "no_change", "reason": "..."}'
    result_json = """{
  "statement": "Отредактированное условие",
  "solution": "Отредактированное решение",
  "answer": "Ответ (без изменений математики)",
  "changes_made": ["список внесённых изменений"]
}"""
    perfect_json = """{
  "statement": "то же условие",
  "solution": "то же решение",
  "answer": "тот же ответ",
  "changes_made": []
}"""

    return f"""Отредактируй задачу. НЕ МЕНЯЙ математику, только улучши оформление.

УСЛОВИЕ:
{statement}

РЕШЕНИЕ:
{solution}

ОТВЕТ: {answer}

═══════════════════════════════════════════════════
КРИТИЧНЫЕ ЗАПРЕТЫ (нарушение = автоматический reject):
- НЕ менять числа, коэффициенты, константы
- НЕ переименовывать переменные (a->x, n->k)
- НЕ добавлять и не удалять шаги решения
- НЕ упрощать и не раскрывать формулы
- НЕ менять логику доказательства
- НЕ исправлять "ошибки" в математике (это не твоя задача)

При ЛЮБОМ сомнении — верни без изменений:
{no_change_json}

═══════════════════════════════════════════════════
ПРАВИЛА РЕДАКТИРОВАНИЯ:

1. LaTeX:
   - Inline: ТОЛЬКО \\( ... \\) (НЕ $...$)
   - Display: ТОЛЬКО \\[ ... \\] (НЕ $$...$$)
   - Проверь парность скобок
   - \\text{{}} для русского текста внутри формул
   - \\ldots вместо ...
   - \\leqslant вместо \\le где уместно

2. Русский язык:
   - Олимпиадный стиль (строгий, но понятный)
   - "Найдите" вместо "Найти" (повелительное наклонение)
   - "Докажите, что" вместо "Доказать, что"
   - Нет сокращений (т.к., т.е. -> "так как", "то есть")
   - Числительные до 10 — словами в условии

3. Структура решения:
   - Каждый логический шаг — отдельный абзац
   - Ключевые формулы — display mode \\[ \\]
   - Промежуточные — inline \\( \\)
   - "Ответ: ..." на отдельной строке в конце

4. НЕ ДЕЛАТЬ:
   - Не менять числа, не исправлять "ошибки" в математике
   - Не добавлять подсказки
   - Не упрощать задачу
   - Не менять ответ

Верни ТОЛЬКО валидный JSON:
{result_json}

Если задача уже идеальна:
{perfect_json}"""
