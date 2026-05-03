#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate services/daily_pool/polisher.py"""
import os

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "services", "daily_pool", "polisher.py")

B1 = chr(123)  # left brace
B2 = chr(125)  # right brace

# Russian strings stored as variables to avoid encoding issues in f-string
SYS_MSG = "Ты — редактор-корректор олимпиадных задач. Твоя задача — финальная полировка текста: исправить LaTeX, улучшить формулировки, убрать лишнее. НЕ менять математическое содержание."

PROMPT_HEADER = "Отредактируй задачу. НЕ МЕНЯЙ математику, только улучши оформление."
LABEL_STATEMENT = "УСЛОВИЕ:"
LABEL_SOLUTION = "РЕШЕНИЕ:"
LABEL_ANSWER = "ОТВЕТ:"
SECTION_BANS = "КРИТИЧНЫЕ ЗАПРЕТЫ (нарушение = автоматический reject):"
BAN1 = "- НЕ менять числа, коэффициенты, константы"
BAN2 = "- НЕ переименовывать переменные (a->x, n->k)"
BAN3 = "- НЕ добавлять и не удалять шаги решения"
BAN4 = "- НЕ упрощать и не раскрывать формулы"
BAN5 = "- НЕ менять логику доказательства"
BAN6 = '- НЕ исправлять "ошибки" в математике (это не твоя задача)'
DOUBT_LINE = 'При ЛЮБОМ сомнении — верни без изменений:'
SECTION_RULES = "ПРАВИЛА РЕДАКТИРОВАНИЯ:"
RULE_LATEX = """1. LaTeX:
   - Inline: ТОЛЬКО \\\\( ... \\\\) (НЕ $...$)
   - Display: ТОЛЬКО \\\\[ ... \\\\] (НЕ $$...$$)
   - Проверь парность скобок
   - \\\\text{{}} для русского текста внутри формул
   - \\\\ldots вместо ...
   - \\\\leqslant вместо \\\\le где уместно"""
RULE_RUSSIAN = """2. Русский язык:
   - Олимпиадный стиль (строгий, но понятный)
   - "Найдите" вместо "Найти" (повелительное наклонение)
   - "Докажите, что" вместо "Доказать, что"
   - Нет сокращений (т.к., т.е. -> "так как", "то есть")
   - Числительные до 10 — словами в условии"""
RULE_STRUCTURE = """3. Структура решения:
   - Каждый логический шаг — отдельный абзац
   - Ключевые формулы — display mode \\\\[ \\\\]
   - Промежуточные — inline \\\\( \\\\)
   - "Ответ: ..." на отдельной строке в конце"""
RULE_DONT = """4. НЕ ДЕЛАТЬ:
   - Не менять числа, не исправлять "ошибки" в математике
   - Не добавлять подсказки
   - Не упрощать задачу
   - Не менять ответ"""

SEP = chr(9552) * 51  # ═ repeated

src = f'''# -*- coding: utf-8 -*-
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

SYSTEM_MSG = """{SYS_MSG}"""


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
        logger.error(f"[Polisher] JSON parse error: {B1}content[:200]{B2}")
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
        logger.info(f"[Polisher] No changes needed: {B1}data.get('reason', ''){B2}")
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
    logger.info(f"[Polisher] {B1}len(changes){B2} changes made, ${B1}result['cost_usd']:.4f{B2}")
    return data


def _build_prompt(statement: str, solution: str, answer: str) -> str:
    """Build the polisher prompt with all rules."""
    no_change_json = '{B1}"status": "no_change", "reason": "..."{B2}'
    result_json = """{B1}
  "statement": "Отредактированное условие",
  "solution": "Отредактированное решение",
  "answer": "Ответ (без изменений математики)",
  "changes_made": ["список внесённых изменений"]
{B2}"""
    perfect_json = """{B1}
  "statement": "то же условие",
  "solution": "то же решение",
  "answer": "тот же ответ",
  "changes_made": []
{B2}"""

    return f"""{PROMPT_HEADER}

{LABEL_STATEMENT}
{B1}statement{B2}

{LABEL_SOLUTION}
{B1}solution{B2}

{LABEL_ANSWER} {B1}answer{B2}

{SEP}
{SECTION_BANS}
{BAN1}
{BAN2}
{BAN3}
{BAN4}
{BAN5}
{BAN6}

{DOUBT_LINE}
{B1}no_change_json{B2}

{SEP}
{SECTION_RULES}

{RULE_LATEX}

{RULE_RUSSIAN}

{RULE_STRUCTURE}

{RULE_DONT}

Верни ТОЛЬКО валидный JSON:
{B1}result_json{B2}

Если задача уже идеальна:
{B1}perfect_json{B2}"""
'''

with open(path, 'w', encoding='utf-8') as f:
    f.write(src)
print(f"Written: {path} ({len(src)} bytes)")
