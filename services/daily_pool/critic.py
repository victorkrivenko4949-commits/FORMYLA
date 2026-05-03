# -*- coding: utf-8 -*-
"""
Critic service: scores problem quality on 5 dimensions.
Threshold: avg >= 8.5 AND min >= 7.
"""
import json
import logging

from services.openrouter_client import openrouter

logger = logging.getLogger(__name__)

MODEL = "anthropic/claude-opus-4.1"
TEMPERATURE = 0.2
AVG_THRESHOLD = 8.5
MIN_THRESHOLD = 7


def review_problem(problem: dict, analysis: dict, position: int) -> dict:
    """
    Review a generated problem.

    Returns: {scores, avg, min, verdict, issues, suggestions, latex_ok}
    """
    style_notes = json.dumps(analysis.get("style_notes", {}), ensure_ascii=False)
    predicted = analysis.get("predicted_variant", [])
    expected_diff = predicted[position - 1].get("difficulty", 5) if position <= len(predicted) else 5

    prompt = f"""ОЛИМПИАДА: {analysis.get('olympiad', '')}, {analysis.get('grade', '')} класс, {analysis.get('round', '')}
ПОЗИЦИЯ В ВАРИАНТЕ: {position}/5
ОЖИДАЕМАЯ СЛОЖНОСТЬ: {expected_diff}/10

ЗАДАЧА:
{problem.get('statement', '')}

РЕШЕНИЕ:
{problem.get('solution', '')}

ОТВЕТ: {problem.get('answer', '')}

ПРОФИЛЬ ОЛИМПИАДЫ:
{style_notes}

Оцени задачу по 5 критериям (1-10 каждый):

1. ОРИГИНАЛЬНОСТЬ (originality): 10=новая идея, 7=свежий поворот, 4=типовая, 1=копия
2. СООТВЕТСТВИЕ СЛОЖНОСТИ (difficulty_match): 10=идеально, 7=чуть отклоняется, 4=заметно, 1=не тот уровень
3. СТИЛЬ (style_match): 10=неотличима от реальной, 7=мелкие отличия, 4=нетипична, 1=другой стиль
4. РЕШАЕМОСТЬ (solvability): 10=элегантное решение, 7=верное, 4=пробелы, 1=неверное
5. ОДНОЗНАЧНОСТЬ (unambiguity): 10=единственная интерпретация, 7=мелкая неточность, 4=две интерпретации, 1=множество трактовок

Также проверь корректность LaTeX (только \\( \\) и \\[ \\]).

Верни ТОЛЬКО валидный JSON:
{{
  "scores": {{
    "originality": число,
    "difficulty_match": число,
    "style_match": число,
    "solvability": число,
    "unambiguity": число
  }},
  "avg": число,
  "min": число,
  "verdict": "approve" или "reject",
  "issues": ["..."],
  "suggestions": ["..."],
  "latex_ok": true/false
}}

Порог: avg >= 8.5 И min >= 7 -> "approve", иначе "reject".
Если latex_ok == false -> автоматический "reject"."""

    result = openrouter.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Ты — строгий рецензент олимпиадных задач. Будь объективен и требователен."},
            {"role": "user", "content": prompt}
        ],
        temperature=TEMPERATURE,
        max_tokens=2048,
    )

    content = result["content"]
    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        data = json.loads(content.strip())
    except json.JSONDecodeError:
        logger.error(f"[Critic] JSON parse error: {content[:200]}")
        raise ValueError("Critic returned invalid JSON")

    # Validate and enforce thresholds
    scores = data.get("scores", {})
    values = list(scores.values())
    if values:
        data["avg"] = round(sum(values) / len(values), 1)
        data["min"] = min(values)
    else:
        data["avg"] = 0
        data["min"] = 0

    # Auto-reject if latex_ok is false
    if not data.get("latex_ok", True):
        data["verdict"] = "reject"
        if "LaTeX некорректен" not in data.get("issues", []):
            data.setdefault("issues", []).append("LaTeX некорректен")

    # Enforce threshold
    if data["avg"] >= AVG_THRESHOLD and data["min"] >= MIN_THRESHOLD and data.get("latex_ok", True):
        data["verdict"] = "approve"
    else:
        data["verdict"] = "reject"

    data["_usage"] = result["usage"]
    data["_cost"] = result["cost_usd"]

    openrouter.log_cost_to_db('critique', MODEL, result['usage'], result['cost_usd'])
    logger.info(f"[Critic] pos={position} avg={data['avg']} min={data['min']} verdict={data['verdict']} ${result['cost_usd']:.4f}")
    return data
