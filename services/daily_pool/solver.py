# -*- coding: utf-8 -*-
"""
Solver service: independently solves a problem and verifies the answer.
Uses o1-pro (Stack A) or o3 (Stack B).
"""
import json
import logging
import re

from services.openrouter_client import openrouter

logger = logging.getLogger(__name__)

from config.models import SOLVER_MODEL, SOLVER_TEMPERATURE

# Single model (no A/B split for MVP)
MODEL = SOLVER_MODEL
TEMPERATURE = SOLVER_TEMPERATURE


def verify_problem(statement: str, expected_answer: str, stack: str = "A") -> dict:
    """
    Solve the problem independently and compare with expected answer.

    Returns: {answer, solution, confidence, is_correct, is_well_posed}
    """
    model = MODEL

    prompt = f"""Реши следующую олимпиадную задачу. Покажи полное решение.

УСЛОВИЕ:
{statement}

Думай шаг за шагом. Проверь ответ подстановкой или другим методом.

Верни ТОЛЬКО валидный JSON:
{{
  "solution": "Полное пошаговое решение с LaTeX",
  "answer": "Краткий финальный ответ",
  "confidence": число от 0.0 до 1.0,
  "verification": "Как проверил ответ",
  "is_well_posed": true или false
}}

Если задача некорректна:
{{
  "solution": "",
  "answer": "",
  "confidence": 0,
  "verification": "",
  "is_well_posed": false,
  "rejection_reason": "Почему задача некорректна"
}}"""

    result = openrouter.chat(
        model=model,
        messages=[
            {"role": "system", "content": "Ты — математик-олимпиадник высшего уровня. Реши задачу С НУЛЯ. LaTeX через \\( \\) и \\[ \\] ТОЛЬКО."},
            {"role": "user", "content": prompt}
        ],
        temperature=TEMPERATURE,
        max_tokens=8192,
    )

    content = result["content"]
    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        data = json.loads(content.strip())
    except json.JSONDecodeError:
        logger.error(f"[Solver] JSON parse error: {content[:200]}")
        raise ValueError("Solver returned invalid JSON")

    # Check well-posedness
    if not data.get("is_well_posed", True):
        data["is_correct"] = False
        data["_usage"] = result["usage"]
        data["_cost"] = result["cost_usd"]
        openrouter.log_cost_to_db('solve', model, result['usage'], result['cost_usd'])
        return data

    # Check confidence
    confidence = data.get("confidence", 0)
    if confidence < 0.7:
        data["is_correct"] = False
        data["_usage"] = result["usage"]
        data["_cost"] = result["cost_usd"]
        openrouter.log_cost_to_db('solve', model, result['usage'], result['cost_usd'])
        logger.warning(f"[Solver] Low confidence: {confidence}")
        return data

    # Compare answers
    solver_answer = data.get("answer", "").strip()
    is_correct = _compare_answers(solver_answer, expected_answer)
    data["is_correct"] = is_correct
    data["_usage"] = result["usage"]
    data["_cost"] = result["cost_usd"]

    openrouter.log_cost_to_db('solve', model, result['usage'], result['cost_usd'])
    logger.info(f"[Solver] stack={stack} correct={is_correct} conf={confidence} ${result['cost_usd']:.4f}")
    return data


def _compare_answers(solver: str, expected: str) -> bool:
    """Compare two answers with normalization."""
    if not solver or not expected:
        return False

    # Normalize
    s = _normalize(solver)
    e = _normalize(expected)

    if s == e:
        return True

    # Numeric comparison
    try:
        if abs(float(s) - float(e)) < 1e-9:
            return True
    except (ValueError, TypeError):
        pass

    # Set comparison (comma-separated)
    s_parts = sorted(_normalize(p) for p in re.split(r'[,;]', solver) if p.strip())
    e_parts = sorted(_normalize(p) for p in re.split(r'[,;]', expected) if p.strip())
    if s_parts == e_parts and len(s_parts) > 1:
        return True

    return False


def _normalize(s: str) -> str:
    """Normalize answer string for comparison."""
    s = s.strip().lower()
    s = re.sub(r'\s+', '', s)
    s = s.replace('\\(', '').replace('\\)', '')
    s = s.replace('\\[', '').replace('\\]', '')
    s = s.replace('\\,', '')
    return s
