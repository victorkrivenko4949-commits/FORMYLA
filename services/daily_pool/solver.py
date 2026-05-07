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


def verify_problem(statement: str, expected_answer: str, stack: str = "A",
                   generator_solution: str = "") -> dict:
    """v2.4 + v2.5: triple-solver with majority threshold + debate tie-breaker.

    Calls each model in SOLVER_MODELS independently.  If at least
    ``SOLVER_MAJORITY_THRESHOLD`` solvers agree with the generator's expected
    answer, we trust them and skip the debate.  Otherwise (correct_count
    below threshold) we trigger
    :func:`services.daily_pool.debate.run_debate` -- a peer-aware R2 round
    plus an arbiter (claude-opus-4.7 by default) that solves the problem
    independently and then rules on equivalence.

    The arbiter's verdict is binding: if it returns ``CORRECT``, we mark
    ``is_correct=True`` even if R1 was 0/3.  The full per-model R1 solutions
    are passed to the debate so peer cross-checking is possible.

    Args:
        statement:         problem text.
        expected_answer:   generator's claimed answer.
        stack:             A/B experiment label (kept for callers).
        generator_solution: full solution text from the generator. Optional
                           but strongly recommended -- the debate uses it as
                           ground-truth context for peer-revision in R2.

    Returns:
        Same shape as v2.4 with these additional keys when debate ran:
            ``_correct_count`` / ``_total_solvers`` (R1 stats),
            ``_debate_triggered`` (bool),
            ``_debate``           (full DebateResult dict, or None),
            ``_high_risk``        (bool, see debate.py for definition).
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
            # v2.5: keep the full solution text so downstream debate can show
            # peers each other's work.  Truncated to keep memory sane.
            "solution": (single.get("solution", "") or "")[:8000],
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
            "_debate_triggered": False, "_debate": None, "_high_risk": False,
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
    best_data["_debate_triggered"] = False
    best_data["_debate"] = None
    best_data["_high_risk"] = False

    # v2.5 tie-breaker: if R1 majority was NOT reached, run debate.
    if not majority_match and n_models > 0:
        try:
            from services.daily_pool.debate import run_debate, DEBATE_ENABLED
        except Exception as e:
            logger.warning(f"[Solver] debate module unavailable: {e}")
            return best_data
        if not DEBATE_ENABLED:
            return best_data
        logger.info(
            f"[Solver] R1={correct_count}/{n_models} below threshold "
            f"{_MAJ}, triggering debate..."
        )
        try:
            debate_result = run_debate(
                statement=statement,
                generator_answer=expected_answer,
                generator_solution=generator_solution or "",
                r1_results=per_model_results,
            )
        except Exception as e:
            logger.exception(f"[Solver] debate failed: {e}")
            return best_data

        best_data["_debate_triggered"] = True
        best_data["_debate"] = debate_result
        best_data["_high_risk"] = bool(debate_result.get("high_risk"))
        # Roll up debate cost into the total reported by solver.
        d_cost = float(debate_result.get("cost", 0.0))
        best_data["_cost"] = total_cost + d_cost
        verdict = debate_result.get("final_verdict")
        # Arbiter is binding.  CORRECT -> we accept generator's answer;
        # WRONG -> reject; UNCLEAR -> fall back to R1 majority (which was
        # False here, so the problem is rejected).
        if verdict == "CORRECT":
            best_data["is_correct"] = True
            logger.info(
                f"[Solver] debate rescued: R1={correct_count}/{n_models} -> "
                f"arbiter CORRECT (high_risk={best_data['_high_risk']})"
            )
        elif verdict == "WRONG":
            best_data["is_correct"] = False
            logger.warning(
                f"[Solver] debate confirms WRONG: "
                f"correct_answer={debate_result.get('correct_answer','?')[:80]}"
            )
        else:
            # UNCLEAR -- be conservative and keep R1 majority result (False).
            logger.warning("[Solver] debate UNCLEAR, keeping R1 result")
        # Try to log the debate attempt to a side table (best-effort).
        try:
            _log_debate_attempt(debate_result, statement, expected_answer,
                                correct_count, n_models)
        except Exception as e:
            logger.warning(f"[Solver] debate logging failed: {e}")

    return best_data


def _log_debate_attempt(debate_result: dict, statement: str,
                        expected_answer: str,
                        r1_correct: int, r1_total: int) -> None:
    """Best-effort persistence of a debate attempt.

    Creates the ``debate_attempts`` table on first call (so we do not need a
    separate Alembic migration for the v2.5 rollout).  Silently swallows any
    DB error -- losing telemetry must NOT break verification.
    """
    try:
        from models import db
    except Exception:
        return  # not in a Flask app context, skip
    try:
        db.session.execute(db.text(
            "CREATE TABLE IF NOT EXISTS debate_attempts ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "statement_excerpt TEXT, "
            "generator_answer TEXT, "
            "r1_correct INTEGER, r1_total INTEGER, "
            "r2_agreement INTEGER, r2_total INTEGER, "
            "final_verdict TEXT, "
            "correct_answer TEXT, "
            "arbiter_model TEXT, "
            "arbiter_solution TEXT, "
            "arbiter_self_consistent INTEGER, "
            "high_risk INTEGER, "
            "cost_usd REAL, "
            "elapsed_sec REAL"
            ")"
        ))
        db.session.execute(db.text(
            "INSERT INTO debate_attempts ("
            "statement_excerpt, generator_answer, "
            "r1_correct, r1_total, r2_agreement, r2_total, "
            "final_verdict, correct_answer, arbiter_model, "
            "arbiter_solution, arbiter_self_consistent, high_risk, "
            "cost_usd, elapsed_sec"
            ") VALUES ("
            ":se, :ga, :r1c, :r1t, :r2a, :r2t, :fv, :ca, :am, :as_, :asc, "
            ":hr, :cu, :es)"
        ), {
            "se": (statement or "")[:500],
            "ga": (expected_answer or "")[:500],
            "r1c": int(r1_correct), "r1t": int(r1_total),
            "r2a": int(debate_result.get("r2_agreement") or 0),
            "r2t": int(debate_result.get("r2_total") or 0),
            "fv": str(debate_result.get("final_verdict", ""))[:30],
            "ca": str(debate_result.get("correct_answer", ""))[:500],
            "am": str(debate_result.get("arbiter_model", ""))[:80],
            "as_": (debate_result.get("arbiter_solution") or "")[:2000],
            "asc": (1 if debate_result.get("arbiter_self_consistent") else 0),
            "hr": (1 if debate_result.get("high_risk") else 0),
            "cu": float(debate_result.get("cost") or 0.0),
            "es": float(debate_result.get("elapsed") or 0.0),
        })
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        raise


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
        max_tokens=16000,
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
    """Compare two answers with semantic normalization (sympy when possible).

    Delegates to :mod:`services.daily_pool.answer_normalizer` which understands
    \\boxed{}, \\dfrac/\\frac/\\tfrac, \\sqrt rationalization, markdown wrappers,
    comma-separated multi-answer sets, and pure numeric tolerance.
    """
    if not solver or not expected:
        return False
    try:
        from services.daily_pool.answer_normalizer import answers_equal
    except Exception as e:
        logger.warning(f"[Solver] answer_normalizer unavailable: {e}; "
                       f"falling back to legacy comparison")
        return _legacy_compare(solver, expected)
    try:
        return answers_equal(solver, expected)
    except Exception as e:
        logger.warning(f"[Solver] answers_equal raised {e}; using legacy")
        return _legacy_compare(solver, expected)


def _legacy_compare(solver: str, expected: str) -> bool:
    """Pre-v2.5 textual comparison kept as a safety fallback."""
    s = _normalize(solver)
    e = _normalize(expected)
    if s == e:
        return True
    try:
        if abs(float(s) - float(e)) < 1e-9:
            return True
    except (ValueError, TypeError):
        pass
    s_parts = sorted(_normalize(p) for p in re.split(r'[,;]', solver) if p.strip())
    e_parts = sorted(_normalize(p) for p in re.split(r'[,;]', expected) if p.strip())
    if s_parts == e_parts and len(s_parts) > 1:
        return True
    return False


def _normalize(s: str) -> str:
    """Normalize answer string for comparison (legacy — used as fallback)."""
    s = s.strip().lower()
    s = re.sub(r'\s+', '', s)
    s = s.replace('\\(', '').replace('\\)', '')
    s = s.replace('\\[', '').replace('\\]', '')
    s = s.replace('\\,', '')
    return s
