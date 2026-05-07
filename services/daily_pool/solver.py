# -*- coding: utf-8 -*-
"""
Solver service: independently solves a problem and verifies the answer.
Model configured via config/models.py (default: o4-mini).
"""
import json
import logging
import re

from services.openrouter_client import openrouter
from services.daily_pool.json_utils import parse_json_with_latex

logger = logging.getLogger(__name__)

from config.models import SOLVER_MODEL, SOLVER_TEMPERATURE
try:
    from config.models import SOLVER_MODELS as _SOLVER_MODELS
except ImportError:
    _SOLVER_MODELS = [SOLVER_MODEL]
try:
    from config.models import SOLVER_MAJORITY_THRESHOLD as _MAJ
except ImportError:
    _MAJ = 1  # back-compat: any_match

# Default single model kept for back-compat callers
MODEL = SOLVER_MODEL
TEMPERATURE = SOLVER_TEMPERATURE


def verify_problem(statement: str, expected_answer: str, stack: str = "A") -> dict:
    """v2.4: triple-solver with majority threshold.

    Calls each model in SOLVER_MODELS independently and returns a single dict
    where is_correct = True iff at least SOLVER_MAJORITY_THRESHOLD solvers
    agree with the generator's expected answer (default: 2 of 3).
    Per-model details under "_solvers". Costs summed in "_cost".
    """
    models_to_try = list(_SOLVER_MODELS) if _SOLVER_MODELS else [MODEL]
    per_model_results = []
    total_cost = 0.0
    aggregate_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    correct_count = 0
    best_data = None
    best_conf = -1.0
    for model in models_to_try:
        try:
            single = _verify_with_model(statement, expected_answer, stack, model)
        except Exception as e:
            logger.warning(f"[Solver] model {model} failed: {e}")
            per_model_results.append({"model": model, "error": str(e)[:200]})
            continue
        per_model_results.append({
            "model": model,
            "is_correct": single.get("is_correct"),
            "confidence": single.get("confidence"),
            "answer": single.get("answer", "")[:200],
        })
        total_cost += single.get("_cost", 0.0)
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            aggregate_usage[k] += single.get("_usage", {}).get(k, 0)
        if single.get("is_correct"):
            correct_count += 1
        # remember best (highest confidence) for legacy fields
        conf = float(single.get("confidence") or 0)
        if conf > best_conf:
            best_conf = conf
            best_data = single

    if best_data is None:
        return {
            "answer": "", "solution": "", "confidence": 0,
            "is_correct": False, "is_well_posed": True,
            "_usage": aggregate_usage, "_cost": total_cost,
            "_solvers": per_model_results,
        }

    n_models = len([r for r in per_model_results if "error" not in r])
    majority_match = correct_count >= _MAJ
    if 0 < correct_count < n_models:
        logger.warning(
            f"[Solver] disagreement: {correct_count}/{n_models} agree, "
            f"threshold={_MAJ} -> majority_match={majority_match}"
        )

    best_data["is_correct"] = majority_match
    best_data["_cost"] = total_cost
    best_data["_usage"] = aggregate_usage
    best_data["_solvers"] = per_model_results
    best_data["_correct_count"] = correct_count
    best_data["_total_solvers"] = n_models
    return best_data


def _verify_with_model(statement: str, expected_answer: str, stack: str,
                       model: str) -> dict:
    """Single-model verify (extracted from original verify_problem)."""

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
        data = parse_json_with_latex(content.strip())
    except (json.JSONDecodeError, Exception):
        # Last resort: extract answer from raw text
        logger.warning(f"[Solver] JSON parse failed, extracting answer from text")
        answer_match = re.search(r'"answer"\s*:\s*"([^"]*)"', content)
        data = dict(
            solution=content[:2000],
            answer=answer_match.group(1) if answer_match else "",
            confidence=0.6,
            verification="JSON parse failed, extracted from raw",
            is_well_posed=True,
        )

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
    logger.info(
        f"[Solver:{model}] stack={stack} correct={is_correct} "
        f"conf={confidence} ${result['cost_usd']:.4f}"
    )
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
