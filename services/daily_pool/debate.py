# -*- coding: utf-8 -*-
"""
v2.5 debate tie-breaker.

Triggered by :func:`services.daily_pool.solver.verify_problem` when the
independent triple-solver vote produces ``correct_count < SOLVER_MAJORITY_THRESHOLD``.

Architecture (anti-anchoring):

  1. ROUND 2 -- the same three solver models receive their own R1 solution,
     the two peer solutions, and the GENERATOR'S full solution + answer.
     Each must produce a revised answer + verdict
     (AGREE_WITH_GENERATOR / DISAGREE).

  2. ARBITER STEP A -- claude-opus-4.7 solves the problem from scratch
     WITHOUT seeing any of the existing solutions (independent solve).

  3. ARBITER STEP B -- the same arbiter compares its OWN answer to the
     generator's answer.  R2 votes are provided only as advisory context;
     the arbiter is explicitly told to override the majority if its own
     independent solve disagrees.  The arbiter's final verdict is binding.

The whole module is intentionally English-prompted so that long Russian
template strings cannot corrupt the source-file streaming pipeline used to
maintain it.  Models are instructed to ANSWER in the language of the
statement (Russian for our pipeline) but to use the English meta-tokens
``AGREE_WITH_GENERATOR`` / ``DISAGREE`` / ``CORRECT`` / ``WRONG`` so we can
parse them robustly.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from services.openrouter_client import openrouter
from services.daily_pool.json_utils import parse_json_with_latex
from services.daily_pool.answer_normalizer import (
    answers_equal, extract_answer, normalize_answer,
)

logger = logging.getLogger(__name__)

# ── Config (with safe defaults if config/models.py is older) ────────────────
try:
    from config.models import (
        ARBITER_MODEL, ARBITER_FALLBACK, ARBITER_TEMPERATURE,
        DEBATE_R2_TEMPERATURE, DEBATE_MAX_TOKENS, DEBATE_ENABLED,
    )
except Exception:
    ARBITER_MODEL = "anthropic/claude-opus-4.7"
    ARBITER_FALLBACK = "anthropic/claude-opus-4.1"
    ARBITER_TEMPERATURE = 0.0
    DEBATE_R2_TEMPERATURE = 0.1
    DEBATE_MAX_TOKENS = 12000
    DEBATE_ENABLED = True

# v2.5 hotfix B3: models that empirically refuse to honor JSON-only output on
# long olympiad reasoning.  For these we skip the json.loads attempt entirely
# and parse the response in free-form mode (extract verdict tokens + answer).
_FREEFORM_FIRST_MODELS = {
    "google/gemini-2.5-pro",
    "google/gemini-2.0-pro",
}


# ── Prompts ─────────────────────────────────────────────────────────────────

_R2_TEMPLATE = """\
You are an olympiad-level mathematician revising your own solution
in light of solutions produced by other experts and the problem author.

PROBLEM:
{statement}

AUTHOR'S (GENERATOR'S) SOLUTION:
{generator_solution}

Author's final answer: {generator_answer}

YOUR PREVIOUS SOLUTION:
{my_r1_solution}

PEER A's SOLUTION:
{peer_a_solution}

PEER B's SOLUTION:
{peer_b_solution}

TASK:
Revise the problem.  Find errors -- in your own work or in others'.
Do NOT agree just because others do; verify each step independently.

Pay particular attention to:
  - the statement and use of key theorems (Stewart, power of a point,
    Ptolemy, Vieta, etc.) including their EXACT formula and signs;
  - arithmetic in every step (substitutions, simplifications);
  - the sign and physical interpretation of the final answer;
  - equivalence of answer forms
    (e.g. 96/sqrt(217) is the same as 96*sqrt(217)/217).

Answer in the SAME language as the problem statement, but use the
English meta-tokens AGREE_WITH_GENERATOR / DISAGREE inside the JSON
verdict field exactly as shown.

Return ONLY a valid JSON object, no surrounding prose:
{{
  "revised_solution": "<your revised solution, may be brief>",
  "revised_answer":   "<your final answer, in LaTeX, prefer \\\\boxed{{...}}>",
  "verdict":          "AGREE_WITH_GENERATOR" or "DISAGREE",
  "reasoning":        "<2-3 sentences: what changed, what error if any>",
  "confidence":       <0.0 to 1.0>
}}
"""

_ARBITER_INDEPENDENT_TEMPLATE = """\
You are the senior arbiter for an olympiad-grading dispute.
First you must solve the problem ENTIRELY ON YOUR OWN, with no
exposure to anyone else's solution.  Be rigorous and check arithmetic.

PROBLEM:
{statement}

Use whatever standard olympiad technique you find most direct
(Stewart, power of a point, coordinate geometry, trigonometry,
generating functions, Vieta, etc.).  Show your full reasoning.
Wrap the final answer in \\boxed{{...}}.

Answer in the SAME language as the problem statement.

Return ONLY a valid JSON object:
{{
  "my_solution":   "<full step-by-step solution>",
  "my_answer":     "<final answer, preferably wrapped in \\\\boxed{{...}}>",
  "methods_used":  ["<short labels of techniques applied>"],
  "confidence":    <0.0 to 1.0>
}}
"""

_ARBITER_COMPARE_TEMPLATE = """\
You are the senior arbiter.  You have ALREADY solved the problem
independently.  Now you must rule whether the author's answer is
mathematically correct.

PROBLEM:
{statement}

YOUR INDEPENDENT ANSWER (from your own solve):
{arbiter_own_answer}

AUTHOR'S (GENERATOR'S) ANSWER:
{generator_answer}

R2 ADVISORY VOTES from three peer solvers (FYI -- they may be wrong;
override them if your own solve disagrees):
{r2_summary}

DECIDE: are your independent answer and the author's answer
MATHEMATICALLY EQUIVALENT?  Different surface forms
(e.g. 96/sqrt(217) vs 96*sqrt(217)/217 vs (96\\sqrt{{217}})/217) ARE
equivalent.  If they differ in value, the author is wrong.

If your own answer disagrees with the R2 majority, briefly explain
why your reasoning takes precedence (override_reason).

Return ONLY a valid JSON object:
{{
  "final_verdict":     "CORRECT" or "WRONG",
  "correct_answer":    "<if WRONG, the truly correct answer; if CORRECT, repeat the author's answer>",
  "equivalence_check": "<one sentence: how you confirmed equivalence or rejection>",
  "override_reason":   "<empty if R2 agrees with you, else why you overrode>"
}}
"""


# ── Low-level helpers ───────────────────────────────────────────────────────

def _extract_freeform_fields(raw: str) -> Dict[str, Any]:
    r"""Best-effort field extraction when JSON parsing is unavailable.

    Pulls common fields used by R2 / arbiter prompts:
      verdict / final_verdict, revised_answer / my_answer / correct_answer,
      revised_solution / my_solution, reasoning, confidence.

    Strategy: regex against ``"key"\s*:\s*"value"`` patterns first; if the
    response is plain prose, fall back to the first ``\boxed{...}`` for
    the answer and the AGREE/DISAGREE/CORRECT/WRONG meta-token for verdict.
    """
    data: Dict[str, Any] = {}
    patterns = {
        "verdict": r'"verdict"\s*:\s*"([^"]+)"',
        "final_verdict": r'"final_verdict"\s*:\s*"([^"]+)"',
        "revised_answer": r'"revised_answer"\s*:\s*"((?:[^"\\]|\\.)*)"',
        "my_answer": r'"my_answer"\s*:\s*"((?:[^"\\]|\\.)*)"',
        "correct_answer": r'"correct_answer"\s*:\s*"((?:[^"\\]|\\.)*)"',
        "reasoning": r'"reasoning"\s*:\s*"((?:[^"\\]|\\.)*)"',
        "equivalence_check": r'"equivalence_check"\s*:\s*"((?:[^"\\]|\\.)*)"',
        "override_reason": r'"override_reason"\s*:\s*"((?:[^"\\]|\\.)*)"',
    }
    for key, pat in patterns.items():
        m = re.search(pat, raw, re.DOTALL)
        if m:
            # un-escape \" and \\ in extracted value
            val = m.group(1).replace('\\"', '"').replace('\\\\', '\\')
            data[key] = val

    # Verdict meta-token fallback (works even on totally non-JSON responses)
    if not data.get("verdict") and not data.get("final_verdict"):
        tok = _extract_token(raw, ("AGREE_WITH_GENERATOR", "DISAGREE",
                                    "CORRECT", "WRONG"))
        if tok:
            if tok in ("CORRECT", "WRONG"):
                data["final_verdict"] = tok
            else:
                data["verdict"] = tok

    # Answer fallback: first \boxed{...}
    if not (data.get("revised_answer") or data.get("my_answer") or
            data.get("correct_answer")):
        m = re.search(r'\\boxed\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}', raw)
        if m:
            data["revised_answer"] = "\\boxed{" + m.group(1) + "}"

    # Confidence fallback (numeric)
    m = re.search(r'"confidence"\s*:\s*([0-9.]+)', raw)
    if m:
        try:
            data["confidence"] = float(m.group(1))
        except ValueError:
            pass

    return data


def _call_json(model: str, prompt: str, temperature: float, max_tokens: int,
               system: str) -> Dict[str, Any]:
    """Call the LLM, parse JSON robustly. Returns a dict that includes raw
    content under ``_raw`` and ``_cost``/``_usage`` from the API.

    v2.5 hotfix: for models in ``_FREEFORM_FIRST_MODELS`` (e.g. gemini-2.5-pro)
    we skip the json.loads attempt entirely and use the free-form extractor,
    because empirically those models never honor JSON-only output for long
    olympiad reasoning -- the JSON path always fell back anyway, wasting an
    extra parse cycle and emitting a noisy WARN per debate.
    """
    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    res = openrouter.chat(
        model=model, messages=msgs,
        temperature=temperature, max_tokens=max_tokens,
    )
    raw = res["content"]

    # B3: gemini-style free-form-first path
    if model in _FREEFORM_FIRST_MODELS:
        data = _extract_freeform_fields(raw)
        data["_freeform_path"] = True
    else:
        body = raw
        if "```json" in body:
            body = body.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in body:
            body = body.split("```", 1)[1].split("```", 1)[0]
        try:
            data = parse_json_with_latex(body.strip())
            if not isinstance(data, dict):
                raise ValueError("not a dict")
        except Exception as e:
            logger.warning(f"[Debate:{model}] JSON parse failed ({e}); "
                           f"falling back to free-form extraction")
            data = _extract_freeform_fields(raw)
            data["_parse_error"] = str(e)[:200]

    data["_raw"] = raw
    data["_cost"] = res.get("cost_usd", 0.0)
    data["_usage"] = res.get("usage", {})
    return data


def _safe(s: Any, limit: int = 6000) -> str:
    """Truncate a possibly-non-string value for prompt embedding."""
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    if len(s) > limit:
        return s[:limit] + "\n... [truncated]"
    return s


def _summarize_r2(r2_results: List[Dict[str, Any]]) -> str:
    lines = []
    for r in r2_results:
        lines.append(
            f"  - [{r.get('model','?')}]  verdict={r.get('verdict','?')}  "
            f"answer={_safe(r.get('revised_answer',''), 120)}  "
            f"conf={r.get('confidence','?')}"
        )
    return "\n".join(lines) if lines else "  (no R2 votes)"


_TOKEN_RE = re.compile(
    r"\b(AGREE_WITH_GENERATOR|DISAGREE|CORRECT|WRONG)\b",
    re.IGNORECASE,
)


def _extract_token(text: str, allowed: tuple) -> Optional[str]:
    if not text:
        return None
    found = _TOKEN_RE.findall(text.upper())
    for tok in found:
        if tok.upper() in (a.upper() for a in allowed):
            return tok.upper()
    return None


# ── R2 (peer-aware revision) ────────────────────────────────────────────────

def _round2(statement: str, generator_answer: str, generator_solution: str,
            r1_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Run the second debate round.  Each solver re-thinks the problem with
    full context (own R1, peer R1's, generator's solution & answer)."""
    out: List[Dict[str, Any]] = []
    n = len(r1_results)
    for i, mine in enumerate(r1_results):
        peers = [r1_results[j] for j in range(n) if j != i]
        # Pad to two peers (defensive)
        while len(peers) < 2:
            peers.append({"model": "(none)", "solution": "(no peer solution available)"})
        peer_a = peers[0]
        peer_b = peers[1]

        prompt = _R2_TEMPLATE.format(
            statement=_safe(statement, 4000),
            generator_solution=_safe(generator_solution, 4000),
            generator_answer=_safe(generator_answer, 300),
            my_r1_solution=_safe(mine.get("solution", ""), 5000),
            peer_a_solution=_safe(peer_a.get("solution", ""), 5000),
            peer_b_solution=_safe(peer_b.get("solution", ""), 5000),
        )

        model = mine.get("model", "?")
        t0 = time.time()
        try:
            data = _call_json(
                model, prompt,
                temperature=DEBATE_R2_TEMPERATURE,
                max_tokens=DEBATE_MAX_TOKENS,
                system="You are a careful olympiad mathematician.",
            )
        except Exception as e:
            logger.warning(f"[Debate R2:{model}] call failed: {e}")
            data = {"_error": str(e)[:200], "_cost": 0.0, "_usage": {},
                    "_raw": ""}
        dt = round(time.time() - t0, 2)

        verdict_raw = str(data.get("verdict", ""))
        verdict = _extract_token(verdict_raw + " " + data.get("_raw", ""),
                                 ("AGREE_WITH_GENERATOR", "DISAGREE")) or "UNCLEAR"
        out.append({
            "model": model,
            "verdict": verdict,
            "revised_answer": _safe(data.get("revised_answer", ""), 400),
            "revised_solution": _safe(data.get("revised_solution", ""), 4000),
            "reasoning": _safe(data.get("reasoning", ""), 800),
            "confidence": data.get("confidence"),
            "_raw": data.get("_raw", ""),
            "_cost": float(data.get("_cost", 0.0)),
            "_usage": data.get("_usage", {}),
            "elapsed": dt,
        })
        logger.info(f"[Debate R2:{model}] verdict={verdict} "
                    f"ans={out[-1]['revised_answer'][:80]} ({dt}s)")
    return out


# ── Arbiter (two stages: independent solve + compare) ───────────────────────

def _arbiter_independent(statement: str) -> Dict[str, Any]:
    prompt = _ARBITER_INDEPENDENT_TEMPLATE.format(
        statement=_safe(statement, 4000),
    )
    last_err: Optional[Exception] = None
    for model in (ARBITER_MODEL, ARBITER_FALLBACK):
        t0 = time.time()
        try:
            data = _call_json(
                model, prompt,
                temperature=ARBITER_TEMPERATURE,
                max_tokens=DEBATE_MAX_TOKENS,
                system=("You are a senior olympiad mathematician acting as a "
                        "binding arbiter. Be rigorous and self-critical."),
            )
            data["_model"] = model
            data["_elapsed"] = round(time.time() - t0, 2)
            return data
        except Exception as e:
            last_err = e
            logger.warning(f"[Arbiter independent:{model}] failed: {e}")
            continue
    return {
        "_error": str(last_err)[:200] if last_err else "unknown",
        "my_solution": "", "my_answer": "", "_cost": 0.0, "_usage": {},
        "_model": "(none)", "_elapsed": 0.0, "_raw": "",
    }


def _arbiter_compare(statement: str, generator_answer: str,
                     arbiter_own_answer: str,
                     r2_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    prompt = _ARBITER_COMPARE_TEMPLATE.format(
        statement=_safe(statement, 4000),
        arbiter_own_answer=_safe(arbiter_own_answer, 400),
        generator_answer=_safe(generator_answer, 300),
        r2_summary=_summarize_r2(r2_results),
    )
    last_err: Optional[Exception] = None
    for model in (ARBITER_MODEL, ARBITER_FALLBACK):
        t0 = time.time()
        try:
            data = _call_json(
                model, prompt,
                temperature=ARBITER_TEMPERATURE,
                max_tokens=4000,
                system=("You are a senior olympiad arbiter. Override majority "
                        "if your own reasoning warrants it."),
            )
            data["_model"] = model
            data["_elapsed"] = round(time.time() - t0, 2)
            return data
        except Exception as e:
            last_err = e
            logger.warning(f"[Arbiter compare:{model}] failed: {e}")
            continue
    return {
        "_error": str(last_err)[:200] if last_err else "unknown",
        "final_verdict": "UNCLEAR", "correct_answer": "?",
        "_cost": 0.0, "_usage": {}, "_model": "(none)", "_elapsed": 0.0,
        "_raw": "",
    }


# ── Public entry point ──────────────────────────────────────────────────────

def run_debate(statement: str,
               generator_answer: str,
               generator_solution: str,
               r1_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Tie-breaker debate.  See module docstring for protocol.

    Args:
        statement: the problem text (Russian or English).
        generator_answer: the generator's claimed answer string.
        generator_solution: the generator's full solution text.
        r1_results: list of dicts from solver R1 with keys at minimum:
            ``model`` (id), ``solution`` (free-form text),
            ``answer`` (claimed answer), ``is_correct`` (bool from R1).

    Returns:
        dict with:
            ``final_verdict``: "CORRECT" / "WRONG" / "UNCLEAR"
            ``correct_answer``: arbiter's binding answer
            ``arbiter_solution``: arbiter's independent solution
            ``arbiter_model``: actual model id used
            ``r2_agreement``: int (number of R2 voters agreeing with generator)
            ``r2_total``: int
            ``r2_results``: list of per-voter dicts (verdict + revised_answer)
            ``high_risk``: True iff R1 was 0/N AND arbiter says CORRECT
            ``cost``: total $ for the debate
            ``elapsed``: total seconds
    """
    t0 = time.time()
    if not DEBATE_ENABLED:
        return {
            "final_verdict": "SKIPPED",
            "correct_answer": generator_answer,
            "arbiter_solution": "",
            "arbiter_model": "(disabled)",
            "r2_agreement": 0,
            "r2_total": 0,
            "r2_results": [],
            "high_risk": False,
            "cost": 0.0,
            "elapsed": 0.0,
            "_skipped_reason": "DEBATE_ENABLED=False",
        }

    cost = 0.0

    # R2
    r2 = _round2(statement, generator_answer, generator_solution or "", r1_results)
    cost += sum(float(r.get("_cost", 0.0)) for r in r2)
    r2_agree = sum(1 for r in r2 if r.get("verdict") == "AGREE_WITH_GENERATOR")
    r2_total = len([r for r in r2 if r.get("verdict") in ("AGREE_WITH_GENERATOR", "DISAGREE")])

    # Arbiter -- independent solve first
    arb_indep = _arbiter_independent(statement)
    cost += float(arb_indep.get("_cost", 0.0))
    arb_own_answer_raw = str(arb_indep.get("my_answer", "") or "")
    arb_own_answer = extract_answer(arb_own_answer_raw) or arb_own_answer_raw

    # Arbiter -- compare
    arb_cmp = _arbiter_compare(statement, generator_answer,
                               arb_own_answer, r2)
    cost += float(arb_cmp.get("_cost", 0.0))

    final_token = _extract_token(
        str(arb_cmp.get("final_verdict", "")) + " " + str(arb_cmp.get("_raw", "")),
        ("CORRECT", "WRONG"),
    )
    final_verdict = final_token or "UNCLEAR"

    # Decide the binding correct_answer.
    declared_correct = str(arb_cmp.get("correct_answer", "")).strip()
    if final_verdict == "CORRECT":
        correct_answer = generator_answer
    elif final_verdict == "WRONG":
        # Prefer arbiter's compare-stage answer; fall back to its independent answer.
        correct_answer = declared_correct or arb_own_answer or "(unknown)"
    else:
        # UNCLEAR -- be conservative, return arbiter's independent answer if any.
        correct_answer = arb_own_answer or generator_answer

    # Sanity check: if final_verdict == CORRECT but arbiter's own independent
    # answer is NOT mathematically equal to the generator's, that is a red flag
    # we should record (potentially an arbiter compare-stage hallucination).
    arb_self_consistent = answers_equal(arb_own_answer, generator_answer) \
        if (arb_own_answer and generator_answer) else None

    # High-risk: R1 had ZERO solver agreement AND arbiter rescued it.
    # (That is exactly the scenario Виктор asked us to flag for downstream review.)
    r1_correct = sum(1 for r in r1_results if r.get("is_correct"))
    high_risk = (r1_correct == 0 and final_verdict == "CORRECT")

    elapsed = round(time.time() - t0, 2)
    logger.info(
        f"[Debate] verdict={final_verdict}  R1={r1_correct}/{len(r1_results)}  "
        f"R2={r2_agree}/{r2_total}  arbiter={arb_indep.get('_model','?')}  "
        f"high_risk={high_risk}  cost=${cost:.4f}  ({elapsed}s)"
    )

    return {
        "final_verdict": final_verdict,
        "correct_answer": correct_answer,
        "arbiter_solution": _safe(arb_indep.get("my_solution", ""), 8000),
        "arbiter_own_answer": arb_own_answer,
        "arbiter_model": arb_indep.get("_model", ARBITER_MODEL),
        "arbiter_self_consistent": arb_self_consistent,
        "arbiter_override_reason": _safe(arb_cmp.get("override_reason", ""), 600),
        "arbiter_equivalence_check": _safe(arb_cmp.get("equivalence_check", ""), 600),
        "r2_agreement": r2_agree,
        "r2_total": r2_total,
        "r2_results": r2,
        "high_risk": high_risk,
        "cost": round(cost, 6),
        "elapsed": elapsed,
        "_arbiter_independent_raw": arb_indep,
        "_arbiter_compare_raw": arb_cmp,
    }
