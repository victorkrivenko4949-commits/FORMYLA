# -*- coding: utf-8 -*-
"""
Generator service: creates a single olympiad problem using GPT-5.
"""
import json
import logging

from services.openrouter_client import openrouter
from services.daily_pool.json_utils import parse_json_with_latex as _parse_json_with_latex

logger = logging.getLogger(__name__)

from config.models import GENERATOR_MODEL as MODEL, GENERATOR_TEMPERATURE as TEMPERATURE


def generate_problem(analysis: dict, position: int, existing_in_variant: list = None,
                     recent_problems: list = None) -> dict:
    """
    Generate a single problem for the given position.

    Args:
        analysis: Full analysis JSON from analyzer
        position: 1-5
        existing_in_variant: Problems already generated for this variant
        recent_problems: Last 5 problems on same topic for dedup

    Returns: dict with keys: statement, solution, answer, topic, difficulty, method, idea_summary
    Raises: ValueError if model returns reject or invalid JSON
    """
    predicted = analysis.get("predicted_variant", [])
    if position > len(predicted):
        raise ValueError(f"Position {position} not in predicted_variant (len={len(predicted)})")

    spec = predicted[position - 1]
    style_notes = json.dumps(analysis.get("style_notes", {}), ensure_ascii=False)
    forbidden = ", ".join(analysis.get("forbidden_topics", []))

    existing_text = ""
    if existing_in_variant:
        for i, p in enumerate(existing_in_variant, 1):
            existing_text += f"  {i}. [{p.get('topic','')}] {p.get('statement','')[:100]}...\n"

    recent_text = ""
    if recent_problems:
        for p in recent_problems[:5]:
            recent_text += f"  - {p[:120]}...\n"

    prompt = f"""ПРОФИЛЬ ОЛИМПИАДЫ:
  Олимпиада: {analysis.get('olympiad', '')}
  Класс: {analysis.get('grade', '')}
  Этап: {analysis.get('round', '')}

ЗАДАНИЕ: Создай задачу для ПОЗИЦИИ {position} из 5.

ТРЕБОВАНИЯ К ЭТОЙ ПОЗИЦИИ:
  Тема: {spec.get('theme', '')}
  Подтема: {spec.get('subtopic', '')}
  Идея: {spec.get('idea', '')}
  Сложность: {spec.get('difficulty', 5)}/10
  Тип ответа: {spec.get('answer_type', 'number')}
  Ожидаемые методы: {', '.join(spec.get('expected_techniques', []))}

СТИЛЬ ОЛИМПИАДЫ:
{style_notes}

ЗАПРЕЩЁННЫЕ ТЕМЫ: {forbidden or 'нет'}

ЗАДАЧИ, КОТОРЫЕ УЖЕ ЕСТЬ В ЭТОМ ВАРИАНТЕ:
{existing_text or '  (пока нет)'}

ПОСЛЕДНИЕ ЗАДАЧИ НА ЭТУ ТЕМУ (не повторять идеи):
{recent_text or '  (нет данных)'}

Думай шаг за шагом:
1. Придумай ОРИГИНАЛЬНУЮ математическую идею
2. Оберни её в условие в стиле этой олимпиады
3. Реши задачу полностью
4. Убедись что ответ однозначный
5. Проверь что сложность соответствует позиции

Верни ТОЛЬКО валидный JSON:
{{
  "statement": "Условие на русском с LaTeX через \\\\( \\\\) и \\\\[ \\\\]",
  "solution": "Полное решение",
  "answer": "Краткий ответ",
  "topic": "тема на русском",
  "difficulty": число 1-10,
  "method": "основной метод",
  "idea_summary": "краткое описание идеи"
}}

Если не можешь — верни: {{"status": "reject", "reason": "..."}}"""

    result = openrouter.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Ты — составитель олимпиадных задач мирового уровня. LaTeX ТОЛЬКО через \\( \\) и \\[ \\]. Язык: русский."},
            {"role": "user", "content": prompt}
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
        data = _parse_json_with_latex(content.strip())
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"[Generator] JSON parse error: {e}")
        raise ValueError(f"Generator returned invalid JSON: {content[:200]}")

    if data.get("status") == "reject":
        raise ValueError(f"Generator rejected: {data.get('reason', 'unknown')}")

    # Validate required fields
    required = ["statement", "solution", "answer"]
    for field in required:
        if not data.get(field):
            raise ValueError(f"Generator missing field: {field}")

    # Attach cost info
    data["_usage"] = result["usage"]
    data["_cost"] = result["cost_usd"]

    openrouter.log_cost_to_db('generate', MODEL, result['usage'], result['cost_usd'])
    logger.info(f"[Generator] pos={position} topic={data.get('topic','')} ${result['cost_usd']:.4f}")
    return data
