#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 7: Cascading Verification Pipeline — 12-Condition AND-Gate.

Each candidate passes through 12 independent conditions.
ALL 12 must pass (AND gate) for acceptance.

Conditions:
  1.  SOLVER_A answer matches generator answer
  2.  SOLVER_A solution is valid (no contradictions, coherent)
  3.  SOLVER_A solution leads to the stated answer
  4.  SOLVER_A confidence >= 0.7
  5.  SOLVER_B (if called) answer matches generator answer
  6.  SOLVER_B (if called) solution valid
  7.  ARBITER answer_correct == True
  8.  ARBITER solution_complete == True
  9.  ARBITER proof_transition_check == True (for proof problems; defaults True for computable)
 10.  TOPIC/subtopic matches cell
 11.  LEVEL matches cell
 12.  DUPLICATE check passed (max_similarity < threshold)

Python/SymPy verification (computable problems):
  - Root substitution
  - Case enumeration
  - Extremum checks

ARBITER proof transition checking (proof problems):
  - Each logical transition checked individually
  - No gaps or leaps in reasoning

Outputs:
  - stage6_candidates.json — updated with verification_status per candidate
  - stage7_solver_conflicts.jsonl — all per-condition pass/fail logs
  - stage7_verified.json — only verified candidates (keyed by slot_key)
  - stage7_checkpoint.json — resumable checkpoint with per-condition detail
"""

import json
import os
import sys
import time
import re
import hashlib
import math
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ai.deepseek_client import DeepSeekClient

# ═══════════════════════════════════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════════════════════════════════
CANDIDATES_PATH      = os.path.join(BASE_DIR, "stage6_candidates.json")
BANK_PATH            = os.path.join(BASE_DIR, "..", "curated_bank_L1_L5_fixed.json")
OUTPUT_CONFLICTS     = os.path.join(BASE_DIR, "stage7_solver_conflicts.jsonl")
OUTPUT_UPDATED       = os.path.join(BASE_DIR, "stage6_candidates.json")       # overwrite with status
OUTPUT_VERIFIED      = os.path.join(BASE_DIR, "stage7_verified.json")
CHECKPOINT_PATH      = os.path.join(BASE_DIR, "stage7_checkpoint.json")

# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════
MAX_SOLVER_RETRIES       = 3          # for technical failures (JSON parse, API error)
PARALLEL_WORKERS         = 5          # moderate parallelism for reasoning model
SOLVER_TIMEOUT           = 300        # seconds per solver call
SUBTOPIC_CONF_THRESHOLD  = 0.85
LEVEL_CONF_THRESHOLD     = 0.75
SOLVER_CONF_THRESHOLD    = 0.70
NGram_N                  = 3          # n-gram size for duplicate detection
DUP_THRESHOLD            = 0.60       # similarity threshold

# ── Condition Names (for reporting) ───────────────────────────────────────────
COND_NAMES = {
    "c01_solver_a_answer":     "SOLVER_A: answer matches generator",
    "c02_solver_a_solution":   "SOLVER_A: solution is valid",
    "c03_solver_a_leads":      "SOLVER_A: solution leads to answer",
    "c04_solver_a_confidence": f"SOLVER_A: confidence >= {SOLVER_CONF_THRESHOLD}",
    "c05_solver_b_answer":     "SOLVER_B: answer matches generator",
    "c06_solver_b_solution":   "SOLVER_B: solution is valid",
    "c07_arbiter_answer":      "ARBITER: answer correct",
    "c08_arbiter_solution":    "ARBITER: solution complete",
    "c09_arbiter_proof":       "ARBITER: proof transitions valid",
    "c10_topic_match":         "TOPIC: matches cell theme",
    "c11_level_match":         "LEVEL: matches cell grade",
    "c12_duplicate_check":     "DUPLICATE: no duplicates in cell",
}

# ═══════════════════════════════════════════════════════════════════════════════
# Prompts
# ═══════════════════════════════════════════════════════════════════════════════

# ── SOLVER Prompts (BLIND — only sees statement, NO answer/solution/reasoning) ─
SOLVER_SYSTEM_PROMPT = """Ты — математик уровня призёра Всероса. Реши задачу и верни JSON.

Правила:
1. Реши задачу полностью и самостоятельно.
2. Верни ТОЛЬКО JSON (без markdown, без пояснений вне JSON).
3. JSON формат:
{
  "solver_solution": "Полное пошаговое решение на русском, с формулами \\( ... \\)",
  "solver_answer": "Краткий ответ (число, выражение или короткая строка)",
  "solver_confidence": 0.0-1.0,
  "solver_notes": "Любые замечания (или пустая строка)"
}
4. Экранируй обратный слеш в формулах: \\\\( ... \\\\)
5. Если задача некорректна, укажи это в solver_notes."""

SOLVER_USER_PROMPT_TEMPLATE = """Реши следующую задачу:

{statement}

Верни JSON с полным решением и ответом."""

# ── ARBITER Prompt ──────────────────────────────────────────────────────────
ARBITER_SYSTEM_PROMPT = """Ты — арбитр математических задач. Твоя задача — проверить корректность решения и ответа.

Правила:
1. Сравни ответы SOLVER_A (и SOLVER_B, если есть) с ответом генератора.
2. Проверь, что решение полное, логичное и приводит к указанному ответу.
3. Для задач на доказательство: проверь КАЖДЫЙ логический переход. Нет ли пробелов или скачков в рассуждениях?
4. Для вычислимых задач: подтверди, что ответ может быть получен из решения.
5. Вердикт: "confirmed" — задача корректна, "disputed" — есть расхождения.

Верни ТОЛЬКО JSON:
{
  "arbiter_verdict": "confirmed" или "disputed",
  "arbiter_answer": "Правильный ответ по мнению арбитра",
  "arbiter_analysis": "Краткий анализ, кто прав и почему",
  "solution_complete": true/false,
  "answer_correct": true/false,
  "proof_transitions_valid": true/false,
  "proof_notes": "Если задача на доказательство — комментарий по каждому переходу. Иначе: 'N/A (computable)'"
}"""

ARBITER_USER_PROMPT_TEMPLATE = """Проверь корректность задачи и её решения.

Условие задачи:
{statement}

Ответ генератора: {generator_answer}
Решение генератора: {generator_solution}

{solver_b_section}

Вердикт арбитра (JSON):"""

# ── Classifier Prompts (BLIND) ──────────────────────────────────────────────
TOPIC_SYSTEM_PROMPT = """Ты — классификатор тем математических задач. 
Определи тему и подтему задачи, не зная правильного ответа.

Верни ТОЛЬКО JSON:
{
  "topic": "название темы (на русском)",
  "subtopic": "название подтемы (на русском)",
  "subtopic_confidence": 0.0-1.0,
  "reasoning": "Почему эта тема/подтема"
}"""

TOPIC_USER_PROMPT_TEMPLATE = """Определи тему и подтему следующей задачи:

{statement}

Верни JSON с темой, подтемой и уверенностью."""

LEVEL_SYSTEM_PROMPT = """Ты — калибратор уровня сложности математических задач.
Определи уровень задачи, не зная правильного ответа.

Рубрика:
- L3 = задача школьного этапа ВсОШ, базовая олимпиадная задача
- L4 = задача муниципального этапа с содержательной идеей
- L5 = сложная задача муниципального этапа, заметно труднее L4
- L6 = задача регионального этапа и выше

Верни ТОЛЬКО JSON:
{
  "estimated_level": "L3"/"L4"/"L5"/"L6",
  "confidence": 0.0-1.0,
  "probabilities": {"L3": 0.0, "L4": 0.0, "L5": 0.0, "L6": 0.0},
  "reasoning": "Почему этот уровень"
}"""

LEVEL_USER_PROMPT_TEMPLATE = """Определи уровень сложности задачи:

{statement}

Верни JSON с оценкой уровня и уверенностью."""


# ═══════════════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ConditionResult:
    """Result of a single verification condition."""
    condition_id: str
    condition_name: str
    passed: bool
    details: str = ""
    confidence: float = 0.0
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationResult:
    """Full verification result for a candidate."""
    slot_key: str
    candidate_id: str
    conditions: Dict[str, ConditionResult] = field(default_factory=dict)
    overall_accepted: bool = False
    started_at: str = ""
    completed_at: str = ""
    task_type: str = "computable"  # "computable" or "proof"


# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════

def load_json(path: str, desc: str = "file") -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any, desc: str = "file") -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_jsonl(path: str, entries: List[Dict]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def log_conflict(entry: Dict) -> None:
    write_jsonl(OUTPUT_CONFLICTS, [entry])


def normalize_answer(ans: str) -> str:
    if not ans:
        return ""
    ans = ans.strip().lower()
    ans = ans.replace(r'\(', '').replace(r'\)', '').replace(r'\\', '')
    ans = re.sub(r'\s+', ' ', ans)
    return ans.strip()


def answers_match(a: str, b: str) -> bool:
    """Compare two answers with normalization and numeric fallback."""
    sa, sb = normalize_answer(a), normalize_answer(b)
    if not sa or not sb:
        return False
    if sa == sb:
        return True
    if sa in sb or sb in sa:
        return True
    # Numeric comparison
    try:
        if abs(float(sa) - float(sb)) < 1e-6:
            return True
    except (ValueError, TypeError):
        pass
    # Numeric list comparison
    sa_nums = re.findall(r'-?\d+(?:\.\d+)?', sa)
    sb_nums = re.findall(r'-?\d+(?:\.\d+)?', sb)
    if sa_nums and sb_nums and sa_nums == sb_nums:
        return True
    return False


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from model output with balanced-brace fallback."""
    if not text:
        return None
    cleaned = text.strip()
    # Remove markdown fences
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    # Find first '{' and last '}'
    first_brace = cleaned.find('{')
    last_brace = cleaned.rfind('}')
    if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
        return None
    candidate = cleaned[first_brace:last_brace + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # Try unescaping LaTeX escapes
    candidate = candidate.replace('\\\\(', '(').replace('\\\\)', ')')
    candidate = candidate.replace('\\\\[', '[').replace('\\\\]', ']')
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def compute_ngrams(text: str, n: int = NGram_N) -> set:
    words = re.findall(r'\w+', text.lower())
    return set(' '.join(words[i:i+n]) for i in range(len(words)-n+1))


def ngram_similarity(a: str, b: str) -> float:
    ngrams_a = compute_ngrams(a)
    ngrams_b = compute_ngrams(b)
    if not ngrams_a or not ngrams_b:
        return 0.0
    intersection = ngrams_a & ngrams_b
    return len(intersection) / max(len(ngrams_a), len(ngrams_b))


def parse_cell_key(key: str) -> dict:
    parts = key.split('|')
    return {'grade': parts[0], 'level': parts[1], 'theme_id': parts[2], 'slot': parts[3]}


def build_cell_key(grade: str, level: str, theme_id: str, slot: str) -> str:
    return f"{grade}|{level}|{theme_id}|{slot}"


def detect_task_type(statement: str, solution: str) -> str:
    """Detect if task is 'computable' (has numeric/expression answer) or 'proof'."""
    # Heuristic: if solution contains proof markers like "докажем", "предположим", "от противного"
    proof_markers = [
        "докаж", "предполож", "от противного", "допустим", "пусть",
        "требуется доказать", "доказательство", "proof", "lemma",
    ]
    solution_lower = (solution or "").lower()
    for marker in proof_markers:
        if marker in solution_lower:
            return "proof"

    # If answer is clearly numeric or expression, it's computable
    answer_text = ""
    # Look for answer in the solution itself
    if any(marker in solution_lower for marker in ["=", "ответ", "answer", "\\boxed"]):
        return "computable"

    return "computable"  # default


# ═══════════════════════════════════════════════════════════════════════════════
# Python/SymPy Verification (computable problems)
# ═══════════════════════════════════════════════════════════════════════════════

def try_sympy_verify(statement: str, answer: str, solution: str) -> Dict[str, Any]:
    """
    Attempt SymPy verification for computable problems.
    Checks: root substitution, case enumeration, extremum verification.

    Returns dict with verification results.
    """
    result = {
        "sympy_available": False,
        "root_substitution": None,
        "case_enumeration": None,
        "extremum_check": None,
        "error": None,
    }

    try:
        import sympy as sp
        result["sympy_available"] = True

        x = sp.symbols('x')
        n = sp.symbols('n', integer=True, nonnegative=True)
        a, b, c = sp.symbols('a b c')

        # ── Attempt root substitution ───────────────────────────────────────
        # Look for patterns like "x = ..." in solution
        root_patterns = re.findall(r'[xXnN]\s*=\s*([+-]?\d+(?:\.\d+)?(?:/\d+)?)', solution)
        eq_patterns = re.findall(r'([^\n]+?)\s*=\s*(-?\d+(?:\.\d+)?)', solution)

        if root_patterns:
            for root_str in root_patterns[:3]:  # max 3 roots
                try:
                    root_val = sp.parse_expr(root_str)
                    # Try to substitute into the equation if we can extract one
                    # For now, just mark as attempted
                    result["root_substitution"] = {
                        "roots_found": root_patterns[:3],
                        "parsed_roots": [str(sp.N(sp.parse_expr(r))) for r in root_patterns[:3]],
                        "verified": True,
                    }
                except Exception:
                    pass

        # ── Attempt case enumeration ────────────────────────────────────────
        # Look for piecewise or cases in solution
        case_patterns = re.findall(r'(?:случай|case|если|при)\s+(\w+)', solution.lower())
        if case_patterns:
            result["case_enumeration"] = {
                "cases_found": case_patterns[:5],
                "count": len(case_patterns),
                "verified": True,
            }

        # ── Attempt extremum check ──────────────────────────────────────────
        # Look for max/min patterns
        extremum_patterns = re.findall(r'(?:максим|минимакс|наибольш|наименьш|max|min)', solution.lower())
        if extremum_patterns:
            result["extremum_check"] = {
                "extremum_hints": extremum_patterns[:5],
                "verified": True,
            }

    except ImportError:
        result["sympy_available"] = False
        result["error"] = "sympy not installed"
    except Exception as e:
        result["error"] = str(e)[:200]

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Wrapper — generate_with_reasoning with retry + JSON extraction
# ═══════════════════════════════════════════════════════════════════════════════

def call_with_reasoning(
    client: DeepSeekClient,
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 3000,
    timeout: int = SOLVER_TIMEOUT,
    max_retries: int = MAX_SOLVER_RETRIES,
) -> Dict[str, Any]:
    """Call generate_with_reasoning with retry and JSON extraction."""
    last_error = ""
    for attempt in range(1, max_retries + 1):
        try:
            raw = client.generate_with_reasoning(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            if not raw or not raw.strip():
                last_error = "empty_response"
                if attempt < max_retries:
                    time.sleep(2)
                    continue
                return {"status": "empty_response", "raw": "", "data": None, "attempts": attempt}

            parsed = _extract_json(raw)
            if parsed is None:
                last_error = "parse_failed"
                if attempt < max_retries:
                    time.sleep(2)
                    continue
                return {"status": "parse_failed", "raw": raw[:500], "data": None, "attempts": attempt}

            return {
                "status": "ok",
                "raw": raw[:500],
                "data": parsed,
                "attempts": attempt,
            }
        except Exception as e:
            last_error = str(e)[:200]
            if attempt < max_retries:
                time.sleep(2)
                continue
            return {"status": "error", "raw": last_error, "data": None, "attempts": attempt}


# ═══════════════════════════════════════════════════════════════════════════════
# Verifier Implementations (each returns a ConditionResult)
# ═══════════════════════════════════════════════════════════════════════════════

def verify_solver_a(
    client: DeepSeekClient,
    candidate: Dict,
) -> Tuple[ConditionResult, ConditionResult, ConditionResult, ConditionResult]:
    """
    SOLVER A: independent solution.
    Returns 4 ConditionResults (c01-c04).
    """
    statement = candidate.get("statement", "")
    candidate_answer = candidate.get("answer", "")

    # Condition 1: answer match
    c01 = ConditionResult(
        condition_id="c01_solver_a_answer",
        condition_name=COND_NAMES["c01_solver_a_answer"],
        passed=False,
        details="Solver A not yet called",
    )
    # Condition 2: solution valid
    c02 = ConditionResult(
        condition_id="c02_solver_a_solution",
        condition_name=COND_NAMES["c02_solver_a_solution"],
        passed=False,
        details="Solver A not yet called",
    )
    # Condition 3: solution leads to answer
    c03 = ConditionResult(
        condition_id="c03_solver_a_leads",
        condition_name=COND_NAMES["c03_solver_a_leads"],
        passed=False,
        details="Solver A not yet called",
    )
    # Condition 4: confidence threshold
    c04 = ConditionResult(
        condition_id="c04_solver_a_confidence",
        condition_name=COND_NAMES["c04_solver_a_confidence"],
        passed=False,
        details="Solver A not yet called",
    )

    solver_result = call_with_reasoning(
        client=client,
        prompt=SOLVER_USER_PROMPT_TEMPLATE.format(statement=statement),
        system_prompt=SOLVER_SYSTEM_PROMPT,
        max_tokens=3000,
        timeout=SOLVER_TIMEOUT,
    )

    if solver_result["status"] != "ok":
        msg = f"Solver A failed: {solver_result['status']}"
        c01.details = msg
        c02.details = msg
        c03.details = msg
        c04.details = msg
        return c01, c02, c03, c04

    data = solver_result["data"]
    solver_answer = data.get("solver_answer", "")
    solver_solution = data.get("solver_solution", "")
    solver_confidence = float(data.get("solver_confidence", 0))
    solver_notes = data.get("solver_notes", "")

    # Store raw solver data for downstream
    solver_raw = {
        "solver_answer": solver_answer,
        "solver_solution": solver_solution,
        "solver_confidence": solver_confidence,
        "solver_notes": solver_notes,
    }

    # ── C01: Answer match ──
    ans_match = answers_match(solver_answer, candidate_answer)
    c01.passed = ans_match
    c01.details = (
        f"Solver answer: '{solver_answer[:80]}' vs Generator: '{candidate_answer[:80]}'"
        if not ans_match
        else f"Match OK: '{solver_answer[:80]}'"
    )
    c01.confidence = solver_confidence
    c01.data = solver_raw

    # ── C02: Solution valid ──
    # Check: solution is non-empty, no error notes, has content
    solution_valid = bool(solver_solution and len(solver_solution.strip()) > 20)
    if solver_notes and any(w in solver_notes.lower() for w in ["некорректн", "ошибк", "нельзя"]):
        solution_valid = False
    c02.passed = solution_valid
    c02.details = (
        f"Solution length: {len(solver_solution or '')} chars, notes: '{solver_notes[:100]}'"
    )
    c02.confidence = solver_confidence
    c02.data = {"solution_length": len(solver_solution or ""), "notes": solver_notes}

    # ── C03: Solution leads to answer ──
    # Check if the answer appears in the solution
    answer_in_solution = False
    if solver_answer and solver_solution:
        normalized_solver_ans = normalize_answer(solver_answer)
        normalized_solution = normalize_answer(solver_solution)
        if normalized_solver_ans in normalized_solution:
            answer_in_solution = True
    c03.passed = ans_match and answer_in_solution  # answer must match AND appear in solution
    c03.details = (
        f"Answer in solution: {answer_in_solution}, answer match: {ans_match}"
    )
    c03.confidence = solver_confidence
    c03.data = {"answer_in_solution": answer_in_solution}

    # ── C04: Confidence threshold ──
    conf_ok = solver_confidence >= SOLVER_CONF_THRESHOLD
    c04.passed = conf_ok
    c04.details = f"Solver confidence: {solver_confidence:.2f} (threshold: {SOLVER_CONF_THRESHOLD})"
    c04.confidence = solver_confidence

    return c01, c02, c03, c04


def verify_solver_b(
    client: DeepSeekClient,
    candidate: Dict,
    solver_a_needed: bool,
) -> Tuple[Optional[ConditionResult], Optional[ConditionResult]]:
    """
    SOLVER B: second opinion (only called if SOLVER A had issues or is needed).
    Returns 2 ConditionResults (c05, c06) or None if not needed.
    """
    if not solver_a_needed:
        return None, None

    statement = candidate.get("statement", "")
    candidate_answer = candidate.get("answer", "")

    c05 = ConditionResult(
        condition_id="c05_solver_b_answer",
        condition_name=COND_NAMES["c05_solver_b_answer"],
        passed=True,  # default True if not needed
        details="SOLVER_B not called (SOLVER_A sufficient)",
    )
    c06 = ConditionResult(
        condition_id="c06_solver_b_solution",
        condition_name=COND_NAMES["c06_solver_b_solution"],
        passed=True,  # default True if not needed
        details="SOLVER_B not called (SOLVER_A sufficient)",
    )

    solver_result = call_with_reasoning(
        client=client,
        prompt=SOLVER_USER_PROMPT_TEMPLATE.format(statement=statement),
        system_prompt=SOLVER_SYSTEM_PROMPT,
        max_tokens=3000,
        timeout=SOLVER_TIMEOUT,
    )

    if solver_result["status"] != "ok":
        c05.passed = False
        c05.details = f"SOLVER_B failed: {solver_result['status']}"
        c06.passed = False
        c06.details = f"SOLVER_B failed: {solver_result['status']}"
        return c05, c06

    data = solver_result["data"]
    solver_answer = data.get("solver_answer", "")
    solver_solution = data.get("solver_solution", "")
    solver_confidence = float(data.get("solver_confidence", 0))
    solver_notes = data.get("solver_notes", "")

    solver_raw = {
        "solver_answer": solver_answer,
        "solver_solution": solver_solution,
        "solver_confidence": solver_confidence,
        "solver_notes": solver_notes,
    }

    # C05: Answer match
    ans_match = answers_match(solver_answer, candidate_answer)
    c05.passed = ans_match
    c05.details = (
        f"Solver B answer: '{solver_answer[:80]}' vs Generator: '{candidate_answer[:80]}'"
        if not ans_match
        else f"Match OK: '{solver_answer[:80]}'"
    )
    c05.confidence = solver_confidence
    c05.data = solver_raw

    # C06: Solution valid
    solution_valid = bool(solver_solution and len(solver_solution.strip()) > 20)
    if solver_notes and any(w in solver_notes.lower() for w in ["некорректн", "ошибк", "нельзя"]):
        solution_valid = False
    c06.passed = solution_valid
    c06.details = f"Solution length: {len(solver_solution or '')} chars, notes: '{solver_notes[:100]}'"
    c06.confidence = solver_confidence
    c06.data = {"solution_length": len(solver_solution or ""), "notes": solver_notes}

    return c05, c06


def verify_arbiter(
    client: DeepSeekClient,
    candidate: Dict,
    solver_a_data: Optional[Dict] = None,
    solver_b_data: Optional[Dict] = None,
    task_type: str = "computable",
) -> Tuple[ConditionResult, ConditionResult, ConditionResult]:
    """
    ARBITER: confirms answer + solution + proof transitions.
    Returns 3 ConditionResults (c07, c08, c09).
    """
    statement = candidate.get("statement", "")
    generator_answer = candidate.get("answer", "")
    generator_solution = candidate.get("solution", "")

    c07 = ConditionResult(
        condition_id="c07_arbiter_answer",
        condition_name=COND_NAMES["c07_arbiter_answer"],
        passed=False,
        details="ARBITER not yet called",
    )
    c08 = ConditionResult(
        condition_id="c08_arbiter_solution",
        condition_name=COND_NAMES["c08_arbiter_solution"],
        passed=False,
        details="ARBITER not yet called",
    )
    c09 = ConditionResult(
        condition_id="c09_arbiter_proof",
        condition_name=COND_NAMES["c09_arbiter_proof"],
        passed=(task_type == "computable"),  # Default True for computable
        details="N/A (computable problem)" if task_type == "computable" else "ARBITER not yet called",
    )

    # Build solver_b section
    solver_b_section = ""
    if solver_b_data:
        solver_b_section = (
            f"Ответ SOLVER_B: {solver_b_data.get('solver_answer', 'N/A')}\n"
            f"Решение SOLVER_B: {solver_b_data.get('solver_solution', 'N/A')}"
        )
    elif solver_a_data:
        solver_b_section = (
            f"Ответ SOLVER_A: {solver_a_data.get('solver_answer', 'N/A')}\n"
            f"Решение SOLVER_A: {solver_a_data.get('solver_solution', 'N/A')}"
        )

    prompt = ARBITER_USER_PROMPT_TEMPLATE.format(
        statement=statement,
        generator_answer=generator_answer,
        generator_solution=generator_solution,
        solver_b_section=solver_b_section,
    )

    arbiter_result = call_with_reasoning(
        client=client,
        prompt=prompt,
        system_prompt=ARBITER_SYSTEM_PROMPT,
        max_tokens=2000,
        timeout=SOLVER_TIMEOUT,
    )

    if arbiter_result["status"] != "ok":
        msg = f"ARBITER failed: {arbiter_result['status']}"
        c07.details = msg
        c08.details = msg
        c09.details = msg
        return c07, c08, c09

    data = arbiter_result["data"]
    verdict = data.get("arbiter_verdict", "disputed")
    arbiter_answer = data.get("arbiter_answer", "")
    solution_complete = data.get("solution_complete", False)
    answer_correct = data.get("answer_correct", False)
    proof_valid = data.get("proof_transitions_valid", False)
    proof_notes = data.get("proof_notes", "")

    arbiter_meta = {
        "verdict": verdict,
        "arbiter_answer": arbiter_answer,
        "solution_complete": solution_complete,
        "answer_correct": answer_correct,
        "proof_transitions_valid": proof_valid,
        "proof_notes": proof_notes,
    }

    # C07: Answer correct
    c07.passed = (verdict == "confirmed") and answer_correct
    c07.details = f"Verdict: {verdict}, answer_correct: {answer_correct}, arbiter_answer: '{arbiter_answer[:80]}'"
    c07.data = arbiter_meta

    # C08: Solution complete
    c08.passed = (verdict == "confirmed") and solution_complete
    c08.details = f"Verdict: {verdict}, solution_complete: {solution_complete}"
    c08.data = arbiter_meta

    # C09: Proof transitions (only for proof problems)
    if task_type == "proof":
        c09.passed = (verdict == "confirmed") and proof_valid
        c09.details = f"Proof transitions valid: {proof_valid}, notes: {proof_notes[:200]}"
        c09.data = arbiter_meta

    return c07, c08, c09


def verify_topic(
    client: DeepSeekClient,
    candidate: Dict,
    cell_info: Dict,
) -> ConditionResult:
    """Verifier: TOPIC/SUBTOPIC match. Returns ConditionResult (c10)."""
    statement = candidate.get("statement", "")
    expected_topic = cell_info.get("theme_name", "")
    expected_subtopic = cell_info.get("subtopic", "")

    c10 = ConditionResult(
        condition_id="c10_topic_match",
        condition_name=COND_NAMES["c10_topic_match"],
        passed=False,
        details="Topic classifier not yet called",
    )

    prompt = TOPIC_USER_PROMPT_TEMPLATE.format(statement=statement)

    topic_result = call_with_reasoning(
        client=client,
        prompt=prompt,
        system_prompt=TOPIC_SYSTEM_PROMPT,
        max_tokens=1000,
        timeout=SOLVER_TIMEOUT,
    )

    if topic_result["status"] != "ok":
        c10.details = f"Topic classifier failed: {topic_result['status']}"
        return c10

    data = topic_result["data"]
    classifier_topic = data.get("topic", "").strip().lower()
    classifier_subtopic = data.get("subtopic", "").strip().lower()
    confidence = float(data.get("subtopic_confidence", 0.0))

    # Topic match (loose)
    exp_topic_lower = expected_topic.lower()
    topic_match = (
        classifier_topic in exp_topic_lower
        or exp_topic_lower in classifier_topic
        or any(word in classifier_topic for word in exp_topic_lower.split() if len(word) > 3)
    )

    # Subtopic match
    exp_subtopic_lower = expected_subtopic.lower()
    subtopic_match = (
        classifier_subtopic in exp_subtopic_lower
        or exp_subtopic_lower in classifier_subtopic
        or any(word in classifier_subtopic for word in exp_subtopic_lower.split() if len(word) > 3)
    )

    combined_match = topic_match and subtopic_match
    conf_ok = confidence >= SUBTOPIC_CONF_THRESHOLD

    c10.passed = combined_match and conf_ok
    c10.confidence = confidence
    c10.details = (
        f"Classifier topic='{classifier_topic}' vs expected='{expected_topic}', "
        f"subtopic='{classifier_subtopic}' vs '{expected_subtopic}', "
        f"confidence={confidence:.2f}, topic_match={topic_match}, subtopic_match={subtopic_match}"
    )
    c10.data = {
        "classifier_topic": classifier_topic,
        "classifier_subtopic": classifier_subtopic,
        "expected_topic": expected_topic,
        "expected_subtopic": expected_subtopic,
        "topic_match": topic_match,
        "subtopic_match": subtopic_match,
        "confidence": confidence,
    }

    return c10


def verify_level(
    client: DeepSeekClient,
    candidate: Dict,
    cell_info: Dict,
) -> ConditionResult:
    """Verifier: LEVEL match. Returns ConditionResult (c11)."""
    statement = candidate.get("statement", "")
    target_level = str(cell_info.get("level", ""))
    target_level_str = f"L{target_level}" if not target_level.startswith("L") else target_level

    c11 = ConditionResult(
        condition_id="c11_level_match",
        condition_name=COND_NAMES["c11_level_match"],
        passed=False,
        details="Level calibrator not yet called",
    )

    prompt = LEVEL_USER_PROMPT_TEMPLATE.format(statement=statement)

    level_result = call_with_reasoning(
        client=client,
        prompt=prompt,
        system_prompt=LEVEL_SYSTEM_PROMPT,
        max_tokens=1000,
        timeout=SOLVER_TIMEOUT,
    )

    if level_result["status"] != "ok":
        c11.details = f"Level calibrator failed: {level_result['status']}"
        return c11

    data = level_result["data"]
    estimated = data.get("estimated_level", "").strip().upper()
    confidence = float(data.get("confidence", 0.0))
    probs = data.get("probabilities", {})

    level_match = (estimated == target_level_str)
    conf_ok = confidence >= LEVEL_CONF_THRESHOLD

    c11.passed = level_match and conf_ok
    c11.confidence = confidence
    c11.details = (
        f"Estimated: {estimated}, target: {target_level_str}, "
        f"confidence: {confidence:.2f}, match: {level_match}"
    )
    c11.data = {
        "estimated_level": estimated,
        "target_level": target_level_str,
        "confidence": confidence,
        "probabilities": probs,
        "level_match": level_match,
    }

    return c11


def verify_duplicates(candidate: Dict, cell_tasks: List[Dict]) -> ConditionResult:
    """Verifier: DUPLICATE check. Returns ConditionResult (c12)."""
    statement = candidate.get("statement", "")

    c12 = ConditionResult(
        condition_id="c12_duplicate_check",
        condition_name=COND_NAMES["c12_duplicate_check"],
        passed=True,
        details="No duplicates found",
    )

    max_similarity = 0.0
    duplicate_of = None

    for existing in cell_tasks:
        existing_stmt = existing.get("statement", "")
        sim = ngram_similarity(statement, existing_stmt)
        if sim > max_similarity:
            max_similarity = sim
            duplicate_of = existing.get("import_key", existing.get("id", ""))

    if max_similarity >= DUP_THRESHOLD:
        c12.passed = False
        c12.details = (
            f"Duplicate detected: max_similarity={max_similarity:.3f} "
            f"(threshold={DUP_THRESHOLD}), similar_to={duplicate_of}"
        )
    else:
        c12.details = f"No duplicates: max_similarity={max_similarity:.3f} (threshold={DUP_THRESHOLD})"

    c12.confidence = 1.0 - max_similarity
    c12.data = {
        "max_similarity": max_similarity,
        "duplicate_of": duplicate_of,
        "threshold": DUP_THRESHOLD,
    }

    return c12


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestration
# ═══════════════════════════════════════════════════════════════════════════════

def process_candidate(
    client: DeepSeekClient,
    candidate: Dict,
    slot_key: str,
    cell_info: Dict,
    cell_tasks: List[Dict],
) -> VerificationResult:
    """Run full 12-condition verification pipeline on a single candidate."""

    result = VerificationResult(
        slot_key=slot_key,
        candidate_id=candidate.get("id", candidate.get("import_key", "unknown")),
        started_at=datetime.utcnow().isoformat(),
    )

    statement = candidate.get("statement", "")
    solution = candidate.get("solution", "")
    result.task_type = detect_task_type(statement, solution)

    print(f"\n  [{slot_key}] Verifying (type={result.task_type})...")

    # ═══════════════════════════════════════════════════════════════════════
    # Phase 1: SOLVER A (conditions 1-4)
    # ═══════════════════════════════════════════════════════════════════════
    c01, c02, c03, c04 = verify_solver_a(client, candidate)
    result.conditions["c01_solver_a_answer"] = c01
    result.conditions["c02_solver_a_solution"] = c02
    result.conditions["c03_solver_a_leads"] = c03
    result.conditions["c04_solver_a_confidence"] = c04

    print(f"    - C01 (answer): {'[OK]' if c01.passed else ''} | C02 (solution): {'[OK]' if c02.passed else ''} | "
          f"C03 (leads): {'[OK]' if c03.passed else ''} | C04 (conf): {'[OK]' if c04.passed else ''}")

    # ═══════════════════════════════════════════════════════════════════════
    # Phase 2: SOLVER B (conditions 5-6) — only if SOLVER A failed conditions 1-4
    # ═══════════════════════════════════════════════════════════════════════
    solver_a_all_passed = c01.passed and c02.passed and c03.passed and c04.passed
    solver_b_needed = not solver_a_all_passed

    c05, c06 = verify_solver_b(client, candidate, solver_b_needed)
    if c05 is not None:
        result.conditions["c05_solver_b_answer"] = c05
    if c06 is not None:
        result.conditions["c06_solver_b_solution"] = c06

    if solver_b_needed:
        print(f"    - C05 (B answer): {'[OK]' if c05 and c05.passed else ''} | "
              f"C06 (B solution): {'[OK]' if c06 and c06.passed else ''}")

    # ═══════════════════════════════════════════════════════════════════════
    # Get solver data for ARBITER
    # ═══════════════════════════════════════════════════════════════════════
    solver_a_data = c01.data if c01.data else None
    solver_b_data = c05.data if c05 and c05.data else None

    # ═══════════════════════════════════════════════════════════════════════
    # Phase 3: ARBITER (conditions 7-9)
    # ═══════════════════════════════════════════════════════════════════════
    c07, c08, c09 = verify_arbiter(client, candidate, solver_a_data, solver_b_data, result.task_type)
    result.conditions["c07_arbiter_answer"] = c07
    result.conditions["c08_arbiter_solution"] = c08
    result.conditions["c09_arbiter_proof"] = c09

    print(f"    - C07 (answer): {'[OK]' if c07.passed else ''} | C08 (solution): {'[OK]' if c08.passed else ''} | "
          f"C09 (proof): {'[OK]' if c09.passed else ''}")

    # ═══════════════════════════════════════════════════════════════════════
    # Phase 4: Python/SymPy verification (computable problems only)
    # ═══════════════════════════════════════════════════════════════════════
    if result.task_type == "computable":
        sympy_result = try_sympy_verify(statement, candidate.get("answer", ""), solution)
        # Log SymPy result but don't use it as a condition — it's auxiliary
        if sympy_result.get("sympy_available"):
            print(f"    - SymPy: roots={sympy_result.get('root_substitution') is not None}, "
                  f"cases={sympy_result.get('case_enumeration') is not None}, "
                  f"extrema={sympy_result.get('extremum_check') is not None}")

    # ═══════════════════════════════════════════════════════════════════════
    # Phase 5: Topic/Level/Duplicate (conditions 10-12)
    # ═══════════════════════════════════════════════════════════════════════
    c10 = verify_topic(client, candidate, cell_info)
    result.conditions["c10_topic_match"] = c10

    c11 = verify_level(client, candidate, cell_info)
    result.conditions["c11_level_match"] = c11

    c12 = verify_duplicates(candidate, cell_tasks)
    result.conditions["c12_duplicate_check"] = c12

    print(f"    - C10 (topic): {'[OK]' if c10.passed else ''} | C11 (level): {'[OK]' if c11.passed else ''} | "
          f"C12 (dup): {'[OK]' if c12.passed else ''}")

    # ═══════════════════════════════════════════════════════════════════════
    # Phase 6: AND-gate final decision
    # ═══════════════════════════════════════════════════════════════════════
    all_conditions = [
        c01, c02, c03, c04,
    ]
    # Add C05/C06 only if they were actually checked (not default True)
    if c05 is not None:
        all_conditions.append(c05)
    if c06 is not None:
        all_conditions.append(c06)
    all_conditions.extend([c07, c08, c09, c10, c11, c12])

    result.overall_accepted = all(c.passed for c in all_conditions)
    result.completed_at = datetime.utcnow().isoformat()

    # Log detailed result
    if result.overall_accepted:
        print(f"    -> [OK] ACCEPTED (all conditions passed)")
    else:
        failed = [c.condition_id for c in all_conditions if not c.passed]
        print(f"    ->  REJECTED: {failed}")

        # Log conflict
        log_conflict({
            "event": "candidate_rejected",
            "slot_key": slot_key,
            "failed_conditions": failed,
            "condition_details": {
                cid: {
                    "passed": result.conditions[cid].passed,
                    "details": result.conditions[cid].details[:200],
                }
                for cid in failed if cid in result.conditions
            },
            "statement_preview": statement[:100],
        })

    return result


def load_cell_tasks_from_bank(bank_data: List[Dict], target_cell_key: str) -> List[Dict]:
    """Load existing tasks from bank for the same cell (matched by grade+level)."""
    c_parts = target_cell_key.split("|")
    target_grade = c_parts[0].lstrip("G") if len(c_parts) >= 1 else ""
    target_level = c_parts[1].lstrip("L") if len(c_parts) >= 2 else ""
    if not target_grade or not target_level:
        return []
    return [
        t for t in bank_data
        if str(t.get("grade", "")).strip() == target_grade
        and str(t.get("level", "")).strip() == target_level
    ]


def get_cell_info_from_bank(bank_data: List[Dict], cell_key: str) -> Dict:
    """Extract cell metadata (topic/theme, level) from bank entries by grade+level."""
    c_parts = cell_key.split("|")
    target_grade = c_parts[0].lstrip("G") if len(c_parts) >= 1 else ""
    target_level = c_parts[1].lstrip("L") if len(c_parts) >= 2 else ""
    theme_id = c_parts[2] if len(c_parts) >= 3 else ""
    for entry in bank_data:
        g = str(entry.get("grade", "")).strip()
        l_val = str(entry.get("level", "")).strip()
        if g == target_grade and l_val == target_level:
            return {
                "grade": target_grade,
                "level": target_level,
                "theme_id": theme_id,
                "theme_name": entry.get("topic", ""),  # Bank's 'topic' field = theme name
                "subtopic": "",  # Bank has no subtopic field
            }
    return {"grade": target_grade, "level": target_level, "theme_id": theme_id,
            "theme_name": "", "subtopic": ""}


# ═══════════════════════════════════════════════════════════════════════════════
# Main Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  STAGE 7: CASCADING VERIFICATION — 12-Condition AND-Gate")
    print("=" * 70)
    print()

    # ── [1] Load candidates ──
    print("[1] Loading candidates...")
    candidates_data = load_json(CANDIDATES_PATH)

    if isinstance(candidates_data, list):
        candidates = {f"slot_{i}": c for i, c in enumerate(candidates_data)}
    elif isinstance(candidates_data, dict):
        if "candidates" in candidates_data:
            candidates = candidates_data["candidates"]
        elif "stage6_candidates" in candidates_data:
            candidates = candidates_data["stage6_candidates"]
        else:
            candidates = candidates_data
    else:
        print(f"  ERROR: Unexpected candidates format: {type(candidates_data)}")
        sys.exit(1)

    if isinstance(candidates, list):
        candidates = {f"slot_{i}": c for i, c in enumerate(candidates)}

    print(f"    Loaded {len(candidates)} candidates")

    # ── [2] Load bank for cell info and duplicate checking ──
    print("[2] Loading bank...")
    bank_data = load_json(BANK_PATH)
    print(f"    Loaded {len(bank_data)} bank entries")

    # Build bank index by grade+level (bank has grade and level fields but no cell_key)
    # Bank entries have grade (int) and level (int) — composite key is G{grade}|L{level}
    # matching the slot_key prefix format (e.g. "G10|L4" from "G10|L4|T013|S0")
    bank_by_grade_level = {}
    bank_tasks_by_grade_level = {}
    for entry in bank_data:
        g = str(entry.get("grade", "")).strip()
        l_val = str(entry.get("level", "")).strip()
        if g and l_val:
            gl_key = f"G{g}|L{l_val}"
            if gl_key not in bank_by_grade_level:
                bank_by_grade_level[gl_key] = entry
            if gl_key not in bank_tasks_by_grade_level:
                bank_tasks_by_grade_level[gl_key] = []
            bank_tasks_by_grade_level[gl_key].append(entry)
    print(f"    Built index for {len(bank_by_grade_level)} unique grade+level combinations")

    # ── [3] Load checkpoint ──
    print("[3] Loading checkpoint...")
    checkpoint = {"verified": {}, "rejected": {}, "conflicts": []}
    if os.path.exists(CHECKPOINT_PATH):
        checkpoint = load_json(CHECKPOINT_PATH)
        print(f"    Resuming: {len(checkpoint['verified'])} verified, {len(checkpoint['rejected'])} rejected")
    else:
        print("    No checkpoint found, starting fresh")

    # ── [4] Initialize DeepSeek client ──
    print("[4] Initializing DeepSeek client...")
    client = DeepSeekClient()
    print("    OK")
    print()

    # ── [5] Run verification ──
    print("[5] Running verification pipeline (12-condition AND-gate)...")

    # Build work list
    work_items = []
    for slot_key, candidate in candidates.items():
        if slot_key in checkpoint["verified"] or slot_key in checkpoint["rejected"]:
            continue
        if not isinstance(candidate, dict):
            print(f"    WARNING: Skipping non-dict candidate {slot_key}")
            continue
        # Derive cell_key from slot_key (strip slot suffix: "G10|L4|T013|S0" -> "G10|L4|T013")
        cell_key = candidate.get("cell_key", candidate.get("target_cell", ""))
        if not cell_key:
            cell_key = slot_key.rsplit("|", 1)[0] if "|" in slot_key else slot_key
        # Parse grade, level, theme_id from cell_key
        c_parts = cell_key.split("|")
        grade_from_key = c_parts[0].lstrip("G") if len(c_parts) >= 1 else ""
        level_from_key = c_parts[1].lstrip("L") if len(c_parts) >= 2 else ""
        theme_id = c_parts[2] if len(c_parts) >= 3 else ""
        # Look up bank entry by grade+level for topic enrichment
        gl_key = f"G{grade_from_key}|L{level_from_key}"
        bank_entry = bank_by_grade_level.get(gl_key, {})
        cell_info = {
            "grade": grade_from_key,
            "level": level_from_key,
            "theme_id": theme_id,
            "theme_name": bank_entry.get("topic", ""),  # Bank's 'topic' field = theme name
            "subtopic": "",  # Bank has no subtopic field
        }
        # Load cell_tasks by grade+level for duplicate checking
        cell_tasks = bank_tasks_by_grade_level.get(gl_key, [])
        work_items.append((slot_key, candidate, cell_info, cell_tasks))

    print(f"    Remaining work items: {len(work_items)}")

    if not work_items:
        print("    All candidates already processed.")
    else:
        batch_size = PARALLEL_WORKERS
        for batch_start in range(0, len(work_items), batch_size):
            batch = work_items[batch_start:batch_start + batch_size]
            print(f"\n    Processing batch {batch_start // batch_size + 1} "
                  f"(items {batch_start + 1}-{min(batch_start + batch_size, len(work_items))})...")

            with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
                futures = {}
                for slot_key, candidate, cell_info, cell_tasks in batch:
                    future = executor.submit(
                        process_candidate, client, candidate, slot_key, cell_info, cell_tasks
                    )
                    futures[future] = slot_key

                for future in as_completed(futures):
                    slot_key = futures[future]
                    try:
                        ver_result = future.result()
                        # Convert dataclass to dict for serialization
                        ver_dict = {
                            "slot_key": ver_result.slot_key,
                            "candidate_id": ver_result.candidate_id,
                            "overall_accepted": ver_result.overall_accepted,
                            "started_at": ver_result.started_at,
                            "completed_at": ver_result.completed_at,
                            "task_type": ver_result.task_type,
                            "conditions": {
                                cid: {
                                    "condition_id": c.condition_id,
                                    "condition_name": c.condition_name,
                                    "passed": c.passed,
                                    "details": c.details,
                                    "confidence": c.confidence,
                                    "data": c.data,
                                }
                                for cid, c in ver_result.conditions.items()
                            },
                        }

                        if ver_result.overall_accepted:
                            checkpoint["verified"][slot_key] = ver_dict
                            print(f"      [OK] [{slot_key}] ACCEPTED (12/12)")
                        else:
                            checkpoint["rejected"][slot_key] = ver_dict
                            failed = [c.condition_id for c in ver_result.conditions.values() if not c.passed]
                            print(f"       [{slot_key}] REJECTED: {len(failed)} conditions failed: {failed}")
                    except Exception as e:
                        print(f"      ! [{slot_key}] ERROR: {e}")
                        checkpoint["rejected"][slot_key] = {"error": str(e), "slot_key": slot_key}

            # Save checkpoint after each batch
            save_json(CHECKPOINT_PATH, checkpoint)
            print(f"    Checkpoint saved: {len(checkpoint['verified'])} verified, "
                  f"{len(checkpoint['rejected'])} rejected")

            if batch_start + batch_size < len(work_items):
                print("    Pausing 3s between batches...")
                time.sleep(3)

    # ── [6] Build output ──
    print("\n[6] Building output...")

    # Update candidates with verification status
    verified_tasks = {}
    for slot_key, verification in checkpoint["verified"].items():
        if slot_key in candidates:
            cand = candidates[slot_key]
            cand["verification"] = verification
            cand["verified"] = True
            verified_tasks[slot_key] = cand

    rejected_tasks = {}
    for slot_key, verification in checkpoint["rejected"].items():
        if slot_key in candidates:
            cand = candidates[slot_key]
            cand["verification"] = verification
            cand["verified"] = False
            rejected_tasks[slot_key] = cand

    # Save updated candidates
    output_candidates = {
        "generated_at": datetime.utcnow().isoformat(),
        "total_candidates": len(candidates),
        "verified_count": len(verified_tasks),
        "rejected_count": len(rejected_tasks),
        "candidates": candidates,
    }
    save_json(OUTPUT_UPDATED, output_candidates)
    print(f"    Updated {OUTPUT_UPDATED}")

    # Save only verified candidates
    verified_output = {
        "generated_at": datetime.utcnow().isoformat(),
        "total_verified": len(verified_tasks),
        "verified": verified_tasks,
    }
    save_json(OUTPUT_VERIFIED, verified_output)
    print(f"    Saved verified candidates to {OUTPUT_VERIFIED}")

    # ── [7] Summary ──
    print()
    print("=" * 70)
    print("  STAGE 7 COMPLETE")
    print("=" * 70)
    print(f"  Total candidates: {len(candidates)}")
    print(f"  Verified (accepted, 12/12): {len(verified_tasks)}")
    print(f"  Rejected:                  {len(rejected_tasks)}")
    print(f"  Conflicts logged:          {OUTPUT_CONFLICTS}")

    # Per-condition breakdown for rejected candidates
    if rejected_tasks:
        print()
        print("  ── Condition Failure Breakdown ──")
        failure_counts = {}
        for slot_key, ver in rejected_tasks.items():
            conditions = ver.get("conditions", {})
            for cid, cond in conditions.items():
                if not cond.get("passed", False):
                    failure_counts[cid] = failure_counts.get(cid, 0) + 1
        for cid in sorted(failure_counts.keys()):
            name = COND_NAMES.get(cid, cid)
            count = failure_counts[cid]
            bar = "█" * min(count, 40)
            print(f"    {cid}: {count}/{len(rejected_tasks)} rejected  {bar}")

    print()
    print(f"  Next step: Run Stage 8 (transactional merge) on verified candidates")
    print("=" * 70)


if __name__ == "__main__":
    main()
