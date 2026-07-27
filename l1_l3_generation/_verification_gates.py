#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
13-step AND-gate verification pipeline for L1-L3 task generation.

Each gate is a standalone function returning (passed: bool, detail: str, gate_data: dict).

Gates (all must pass for acceptance):
   1. schema_gate        — JSON structure check (statement, answer, solution)
   2. uniqueness_gate    — task_id not already used in this cell
   3. solver_a_gate      — DeepSeek Reasoner solves independently → answer_a
   4. solver_b_gate      — DeepSeek Reasoner (different prompt) → answer_b
   5. answer_compare_gate— A ≈ B ≈ candidate.answer
   6. solution_verify_gate—A/B solutions have no contradictions
   7. topic_class_gate   — classifier assigns expected topic
   8. subtopic_class_gate— classifier assigns expected subtopic
   9. level_class_gate   — classifier assigns expected level
  10. level_arbiter_gate — resolve L1/L2/L3 mismatches
  11. exact_dup_gate     — no exact text match in existing tasks
  12. template_dup_gate  — no template-level structural similarity
  13. content_arbiter_gate— final verdict (all gates → ACCEPT)
"""

import os
import sys
import json
import time
import hashlib
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

# ============================================================================
# Configuration
# ============================================================================

API_BASE = "https://api.deepseek.com"
MODEL_NAME = "deepseek-reasoner"
API_TIMEOUT = 120          # seconds per API call
SOLVER_TIMEOUT = 180       # solver needs more time

# Gate-level configuration
MAX_SCHEMA_RETRIES = 2
SOLVER_TEMPERATURE_A = 0.3   # deterministic solver
SOLVER_TEMPERATURE_B = 0.5   # slightly different approach
CLASSIFIER_TEMPERATURE = 0.2 # deterministic classifier


# ============================================================================
# Helpers
# ============================================================================

def _call_deepseek(
    api_key: str,
    messages: list,
    model: str = MODEL_NAME,
    timeout: int = API_TIMEOUT,
    max_tokens: int = 2048,
) -> Tuple[bool, Any]:
    """Make a chat completion call. Returns (success, result)."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    t0 = time.time()
    try:
        req = urllib.request.Request(
            f"{API_BASE}/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        body = resp.read().decode("utf-8")
        data = json.loads(body)
        elapsed = (time.time() - t0) * 1000

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "")
        finish_reason = choice.get("finish_reason", "")
        usage = data.get("usage", {})

        if not content:
            return False, {
                "error": f"Empty content, finish_reason={finish_reason}",
                "elapsed_ms": round(elapsed, 1),
            }

        return True, {
            "content": content,
            "finish_reason": finish_reason,
            "usage": usage,
            "elapsed_ms": round(elapsed, 1),
        }

    except urllib.error.HTTPError as e:
        elapsed = (time.time() - t0) * 1000
        body = e.read().decode("utf-8", errors="replace")[:500]
        return False, {
            "error": f"HTTP {e.code}: {body}",
            "elapsed_ms": round(elapsed, 1),
        }
    except json.JSONDecodeError as e:
        elapsed = (time.time() - t0) * 1000
        return False, {
            "error": f"JSON parse failure: {e}",
            "elapsed_ms": round(elapsed, 1),
        }
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        return False, {
            "error": f"Request failure: {e}",
            "elapsed_ms": round(elapsed, 1),
        }


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from model output with balanced-brace fallback."""
    text = text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        clean = []
        for line in lines:
            if line.strip().startswith("```"):
                continue
            clean.append(line)
        text = "\n".join(clean).strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Balanced brace search
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue

    return None


def _normalize_answer(ans: str) -> str:
    """Normalize an answer for comparison: strip whitespace, lowercase,
    remove punctuation, normalize spaces."""
    ans = ans.strip().lower()
    ans = re.sub(r'[^\w\s]', '', ans)
    ans = re.sub(r'\s+', ' ', ans).strip()
    return ans


def _answers_match(a: str, b: str) -> bool:
    """Compare two answers with normalization and numeric fallback."""
    if not a or not b:
        return False

    a_norm = _normalize_answer(a)
    b_norm = _normalize_answer(b)

    # Exact match after normalization
    if a_norm == b_norm:
        return True

    # Try numeric comparison
    try:
        a_num = float(a_norm.replace(',', '.'))
        b_num = float(b_norm.replace(',', '.'))
        return abs(a_num - b_num) < 1e-9
    except (ValueError, TypeError):
        pass

    return False


def _make_gate_result(
    gate_name: str,
    passed: bool,
    detail: str,
    extra: Optional[dict] = None,
) -> dict:
    """Build a standardized gate result."""
    return {
        "gate": gate_name,
        "passed": passed,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **(extra or {}),
    }


def _is_technical_error(result: Any) -> bool:
    """Check if a result represents a technical error (not content rejection)."""
    if isinstance(result, dict):
        error = result.get("error", "")
        return any(kw in error.lower() for kw in [
            "timeout", "dns", "tcp", "tls", "http 429", "http 500",
            "http 502", "http 503", "http 504", "connection refused",
            "eof occurred", "ssl", "network", "rate limit",
        ])
    return False


# ============================================================================
# GATE 1: Schema Validation
# ============================================================================

def gate_schema(candidate: dict) -> dict:
    """GATE 1: Validate required fields and basic structure."""
    errors = []
    required = ["statement", "answer", "solution"]

    for field in required:
        if field not in candidate:
            errors.append(f"Missing field: {field}")
        elif not isinstance(candidate[field], str) or not candidate[field].strip():
            errors.append(f"Field '{field}' is empty or not a string")

    if not errors:
        statement = candidate["statement"].strip()
        answer = candidate["answer"].strip()
        solution = candidate["solution"].strip()

        if len(statement) < 20:
            errors.append(f"Statement too short ({len(statement)} chars, min 20)")
        if len(answer) < 1:
            errors.append("Answer is empty")
        if len(solution) < 50:
            errors.append(f"Solution too short ({len(solution)} chars, min 50)")

    passed = len(errors) == 0
    return _make_gate_result(
        "schema", passed,
        "OK" if passed else "; ".join(errors),
        {"errors": errors} if errors else {},
    )


# ============================================================================
# GATE 2: Uniqueness Check
# ============================================================================

def gate_uniqueness(task_id: str, existing_ids: set) -> dict:
    """GATE 2: Ensure task_id is not already used in this cell."""
    passed = task_id not in existing_ids
    return _make_gate_result(
        "uniqueness", passed,
        f"task_id {task_id} is unique" if passed else f"DUPLICATE task_id: {task_id}",
        {"task_id": task_id},
    )


# ============================================================================
# GATE 3: Solver A (Independent Solution)
# ============================================================================

def gate_solver_a(api_key: str, statement: str) -> dict:
    """GATE 3: DeepSeek solves the problem independently (deterministic)."""
    messages = [
        {
            "role": "system",
            "content": (
                "Ты — математик. Реши задачу шаг за шагом и дай ответ. "
                "Отвечай строго в JSON: {\"answer\": \"...\", \"solution\": \"...\"}"
            ),
        },
        {
            "role": "user",
            "content": f"Реши задачу:\n\n{statement}\n\n"
                        f"Верни JSON с полями answer и solution.",
        },
    ]

    success, result = _call_deepseek(api_key, messages, timeout=SOLVER_TIMEOUT, max_tokens=4096)

    if not success:
        error_msg = result.get("error", "Unknown error")
        is_tech = _is_technical_error(result)
        return _make_gate_result(
            "solver_a", False,
            f"TECHNICAL_ERROR: {error_msg}" if is_tech else f"FAIL: {error_msg}",
            {"is_technical_error": is_tech, "error": error_msg},
        )

    content = result["content"]
    parsed = _extract_json(content)

    if not parsed or "answer" not in parsed:
        return _make_gate_result(
            "solver_a", False,
            "Could not extract answer from solver A",
            {"raw_content_preview": content[:300]},
        )

    solver_answer = str(parsed["answer"]).strip()
    solver_solution = str(parsed.get("solution", "")).strip()

    if not solver_answer:
        return _make_gate_result(
            "solver_a", False,
            "Solver A returned empty answer",
        )

    return _make_gate_result(
        "solver_a", True,
        f"Solver A produced answer (len={len(solver_answer)})",
        {
            "solver_answer": solver_answer,
            "solver_solution": solver_solution,
            "usage": result.get("usage", {}),
            "elapsed_ms": result.get("elapsed_ms"),
        },
    )


# ============================================================================
# GATE 4: Solver B (Alternative Approach)
# ============================================================================

def gate_solver_b(api_key: str, statement: str) -> dict:
    """GATE 4: DeepSeek solves with a different prompt / approach."""
    messages = [
        {
            "role": "system",
            "content": (
                "Ты — эксперт по олимпиадной математике. Проверь своё решение "
                "двумя разными способами и дай окончательный ответ. "
                "Формат JSON: {\"answer\": \"...\", \"approach\": \"...\", \"solution\": \"...\"}"
            ),
        },
        {
            "role": "user",
            "content": f"Вот задача:\n\n{statement}\n\n"
                        f"Проверь двумя разными подходами. "
                        f"Верни JSON: answer, approach, solution.",
        },
    ]

    success, result = _call_deepseek(api_key, messages, timeout=SOLVER_TIMEOUT, max_tokens=4096)

    if not success:
        error_msg = result.get("error", "Unknown error")
        is_tech = _is_technical_error(result)
        return _make_gate_result(
            "solver_b", False,
            f"TECHNICAL_ERROR: {error_msg}" if is_tech else f"FAIL: {error_msg}",
            {"is_technical_error": is_tech, "error": error_msg},
        )

    content = result["content"]
    parsed = _extract_json(content)

    if not parsed or "answer" not in parsed:
        return _make_gate_result(
            "solver_b", False,
            "Could not extract answer from solver B",
            {"raw_content_preview": content[:300]},
        )

    solver_answer = str(parsed["answer"]).strip()
    solver_solution = str(parsed.get("solution", parsed.get("approach", ""))).strip()

    if not solver_answer:
        return _make_gate_result(
            "solver_b", False,
            "Solver B returned empty answer",
        )

    return _make_gate_result(
        "solver_b", True,
        f"Solver B produced answer (len={solver_answer})",
        {
            "solver_answer": solver_answer,
            "solver_solution": solver_solution,
            "usage": result.get("usage", {}),
            "elapsed_ms": result.get("elapsed_ms"),
        },
    )


# ============================================================================
# GATE 5: Answer Comparison
# ============================================================================

def gate_answer_compare(
    candidate_answer: str,
    solver_a_answer: str,
    solver_b_answer: str,
) -> dict:
    """GATE 5: Compare candidate answer with solver A and B answers."""
    a_vs_candidate = _answers_match(solver_a_answer, candidate_answer)
    b_vs_candidate = _answers_match(solver_b_answer, candidate_answer)
    a_vs_b = _answers_match(solver_a_answer, solver_b_answer)

    # Requires at least 2 of 3 comparisons to match
    agreements = sum([a_vs_candidate, b_vs_candidate, a_vs_b])

    if agreements >= 2:
        return _make_gate_result(
            "answer_compare", True,
            f"Answers agree ({agreements}/3 matches)",
            {
                "candidate_vs_solver_a": a_vs_candidate,
                "candidate_vs_solver_b": b_vs_candidate,
                "solver_a_vs_solver_b": a_vs_b,
            },
        )

    return _make_gate_result(
        "answer_compare", False,
        f"Answer mismatch: only {agreements}/3 agreements. "
        f"Candidate='{candidate_answer[:50]}', "
        f"SolverA='{solver_a_answer[:50]}', "
        f"SolverB='{solver_b_answer[:50]}'",
        {
            "candidate_answer": candidate_answer,
            "solver_a_answer": solver_a_answer,
            "solver_b_answer": solver_b_answer,
            "candidate_vs_solver_a": a_vs_candidate,
            "candidate_vs_solver_b": b_vs_candidate,
            "solver_a_vs_solver_b": a_vs_b,
        },
    )


# ============================================================================
# GATE 6: Solution Verification
# ============================================================================

def gate_solution_verify(
    solver_a_solution: str,
    solver_b_solution: str,
) -> dict:
    """GATE 6: Verify solutions from A and B don't contradict each other.
    
    This is a lightweight check — we verify both solutions exist,
    have reasonable length, and don't contain explicit contradictions.
    Full logical verification is done by the solver agreement.
    """
    if not solver_a_solution or len(solver_a_solution) < 50:
        return _make_gate_result(
            "solution_verify", False,
            f"Solver A solution too short ({len(solver_a_solution)} chars)",
        )

    if not solver_b_solution or len(solver_b_solution) < 50:
        return _make_gate_result(
            "solution_verify", False,
            f"Solver B solution too short ({len(solver_b_solution)} chars)",
        )

    # Check for explicit contradictions
    contradictions = []
    for keyword in ["неверно", "ошибка", "противоречие", "incorrect", "error", "contradiction"]:
        if keyword in solver_a_solution.lower() and keyword in solver_b_solution.lower():
            contradictions.append(keyword)

    if len(contradictions) > 1:
        return _make_gate_result(
            "solution_verify", False,
            f"Both solutions contain contradiction keywords: {contradictions}",
        )

    return _make_gate_result(
        "solution_verify", True,
        f"Solutions verified (A: {len(solver_a_solution)} chars, B: {len(solver_b_solution)} chars)",
        {
            "solver_a_solution_len": len(solver_a_solution),
            "solver_b_solution_len": len(solver_b_solution),
        },
    )


# ============================================================================
# GATE 7: Topic Classification
# ============================================================================

def gate_topic_class(api_key: str, statement: str, expected_topic: str) -> dict:
    """GATE 7: Classify the task's topic and verify it matches expected."""
    messages = [
        {
            "role": "system",
            "content": (
                "Ты — классификатор тем олимпиадных задач по математике. "
                "Определи, к какой теме относится задача. "
                "Отвечай только названием темы, без объяснений."
            ),
        },
        {
            "role": "user",
            "content": f"Определи тему задачи:\n\n{statement}\n\n"
                        f"Ожидаемая тема: {expected_topic}\n"
                        f"Ответь только названием темы.",
        },
    ]

    success, result = _call_deepseek(api_key, messages, timeout=30, max_tokens=256)

    if not success:
        error_msg = result.get("error", "Unknown error")
        is_tech = _is_technical_error(result)
        return _make_gate_result(
            "topic_class", False,
            f"TECHNICAL_ERROR: {error_msg}" if is_tech else f"FAIL: {error_msg}",
            {"is_technical_error": is_tech},
        )

    classified = result["content"].strip().lower()
    expected_lower = expected_topic.lower()

    # Fuzzy match — check if expected topic is contained in classified or vice versa
    match = expected_lower in classified or classified in expected_lower

    if match:
        return _make_gate_result(
            "topic_class", True,
            f"Topic classified as '{classified}' (expected '{expected_topic}')",
            {"classified": classified, "expected": expected_topic},
        )

    return _make_gate_result(
        "topic_class", False,
        f"Topic mismatch: classified='{classified}', expected='{expected_topic}'",
        {"classified": classified, "expected": expected_topic},
    )


# ============================================================================
# GATE 8: Subtopic Classification
# ============================================================================

def gate_subtopic_class(api_key: str, statement: str, expected_subtopic: str) -> dict:
    """GATE 8: Classify the task's subtopic and verify it matches expected."""
    messages = [
        {
            "role": "system",
            "content": (
                "Ты — классификатор подтем олимпиадных задач по математике. "
                "Определи, к какой подтеме относится задача. "
                "Отвечай только названием подтемы, без объяснений."
            ),
        },
        {
            "role": "user",
            "content": f"Определи подтему задачи:\n\n{statement}\n\n"
                        f"Ожидаемая подтема: {expected_subtopic}\n"
                        f"Ответь только названием подтемы.",
        },
    ]

    success, result = _call_deepseek(api_key, messages, timeout=30, max_tokens=256)

    if not success:
        error_msg = result.get("error", "Unknown error")
        is_tech = _is_technical_error(result)
        return _make_gate_result(
            "subtopic_class", False,
            f"TECHNICAL_ERROR: {error_msg}" if is_tech else f"FAIL: {error_msg}",
            {"is_technical_error": is_tech},
        )

    classified = result["content"].strip().lower()
    expected_lower = expected_subtopic.lower()

    match = expected_lower in classified or classified in expected_lower

    if match:
        return _make_gate_result(
            "subtopic_class", True,
            f"Subtopic classified as '{classified}'",
            {"classified": classified, "expected": expected_subtopic},
        )

    return _make_gate_result(
        "subtopic_class", False,
        f"Subtopic mismatch: classified='{classified}', expected='{expected_subtopic}'",
        {"classified": classified, "expected": expected_subtopic},
    )


# ============================================================================
# GATE 9: Level Classification
# ============================================================================

def gate_level_class(api_key: str, statement: str, expected_level: str) -> dict:
    """GATE 9: Classify the task's difficulty level."""
    messages = [
        {
            "role": "system",
            "content": (
                "Ты — классификатор уровня сложности олимпиадных задач.\n"
                "L1 = обычная школа, 5-10 минут, базовая программа\n"
                "L2 = сильная школа, 10-20 минут, повышенная сложность\n"
                "L3 = олимпиадный уровень, 20-40 минут, сложная задача\n"
                "Ответь только названием уровня: L1, L2 или L3."
            ),
        },
        {
            "role": "user",
            "content": f"Определи уровень сложности задачи:\n\n{statement}\n\n"
                        f"Ожидаемый уровень: {expected_level}\n"
                        f"Ответь только названием уровня (L1/L2/L3).",
        },
    ]

    success, result = _call_deepseek(api_key, messages, timeout=30, max_tokens=256)

    if not success:
        error_msg = result.get("error", "Unknown error")
        is_tech = _is_technical_error(result)
        return _make_gate_result(
            "level_class", False,
            f"TECHNICAL_ERROR: {error_msg}" if is_tech else f"FAIL: {error_msg}",
            {"is_technical_error": is_tech},
        )

    classified = result["content"].strip().upper()
    expected_upper = expected_level.upper()

    match = classified == expected_upper

    if match:
        return _make_gate_result(
            "level_class", True,
            f"Level classified as '{classified}'",
            {"classified": classified, "expected": expected_level},
        )

    return _make_gate_result(
        "level_class", False,
        f"Level mismatch: classified='{classified}', expected='{expected_level}'",
        {"classified": classified, "expected": expected_level},
    )


# ============================================================================
# GATE 10: Level Arbiter (resolve L1/L2/L3 mismatches)
# ============================================================================

def gate_level_arbiter(api_key: str, statement: str, expected_level: str) -> dict:
    """GATE 10: When classifier and expected level differ, arbitrate via LLM."""
    messages = [
        {
            "role": "system",
            "content": (
                "Ты — арбитр уровня сложности олимпиадных задач.\n"
                "Проанализируй задачу и определи её уровень сложности.\n"
                "L1 = базовая школа, 5-10 минут\n"
                "L2 = сильная школа, 10-20 минут\n"
                "L3 = олимпиадный уровень, 20-40 минут\n"
                "Ответь ТОЛЬКО одним словом: L1, L2 или L3."
            ),
        },
        {
            "role": "user",
            "content": f"Задача:\n\n{statement}\n\n"
                        f"Заявленный уровень: {expected_level}\n"
                        f"Определи истинный уровень сложности.",
        },
    ]

    success, result = _call_deepseek(api_key, messages, timeout=30, max_tokens=256)

    if not success:
        error_msg = result.get("error", "Unknown error")
        is_tech = _is_technical_error(result)
        return _make_gate_result(
            "level_arbiter", False,
            f"TECHNICAL_ERROR: {error_msg}" if is_tech else f"FAIL: {error_msg}",
            {"is_technical_error": is_tech},
        )

    arbiter_verdict = result["content"].strip().upper()
    match = arbiter_verdict == expected_level.upper()

    return _make_gate_result(
        "level_arbiter", match,
        f"Arbiter verdict: {arbiter_verdict} (expected: {expected_level})"
        if not match else f"Arbiter confirms level {expected_level}",
        {"arbiter_verdict": arbiter_verdict, "expected": expected_level},
    )


# ============================================================================
# GATE 11: Exact Duplicate Check
# ============================================================================

def gate_exact_dup(statement: str, existing_statements: List[str]) -> dict:
    """GATE 11: Check for exact text match against existing tasks."""
    norm_statement = _normalize_answer(statement)

    for idx, existing in enumerate(existing_statements):
        norm_existing = _normalize_answer(existing)
        if norm_statement == norm_existing:
            return _make_gate_result(
                "exact_dup", False,
                f"Exact duplicate found (index {idx})",
                {"duplicate_index": idx},
            )

    return _make_gate_result(
        "exact_dup", True,
        f"No exact duplicates found among {len(existing_statements)} existing tasks",
        {"checked_count": len(existing_statements)},
    )


# ============================================================================
# GATE 12: Template Duplicate Check
# ============================================================================

def _template_hash(text: str) -> str:
    """Generate a template-structure hash by replacing numbers/operators with placeholders."""
    # Replace numbers with <NUM>
    t = re.sub(r'\b\d+\b', '<NUM>', text)
    # Replace math operators
    t = re.sub(r'[+\-*/=×÷±]', '<OP>', t)
    # Normalize whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    # Hash
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]


def gate_template_dup(statement: str, existing_statements: List[str], threshold: float = 0.85) -> dict:
    """GATE 12: Detect template-level structural similarity."""
    statement_hash = _template_hash(statement)
    matches = []

    for idx, existing in enumerate(existing_statements):
        existing_hash = _template_hash(existing)
        if statement_hash == existing_hash:
            matches.append(idx)

    if matches:
        return _make_gate_result(
            "template_dup", False,
            f"Template-level duplicate with {len(matches)} existing task(s): indices {matches}",
            {"duplicate_indices": matches, "template_hash": statement_hash},
        )

    return _make_gate_result(
        "template_dup", True,
        f"No template duplicates among {len(existing_statements)} existing tasks",
        {"template_hash": statement_hash, "checked_count": len(existing_statements)},
    )


# ============================================================================
# GATE 13: Content Arbiter (Final Verdict)
# ============================================================================

def gate_content_arbiter(gate_results: Dict[str, dict]) -> dict:
    """GATE 13: Combine all gate results into final ACCEPT / REJECT verdict.

    All gates must pass for ACCEPT. If any gate failed, the result is REJECT
    with a summary of which gates failed and why.
    """
    failed_gates = []
    gate_summary = {}

    for gate_name, result in gate_results.items():
        passed = result.get("passed", False)
        detail = result.get("detail", "No detail")
        gate_summary[gate_name] = {
            "passed": passed,
            "detail": detail,
        }
        if not passed:
            failed_gates.append(gate_name)

    passed = len(failed_gates) == 0

    if passed:
        detail = "ALL 13 GATES PASSED → ACCEPT"
    else:
        failed_names = ", ".join(failed_gates)
        detail = f"REJECTED: gates [{failed_names}] failed"

    return _make_gate_result(
        "content_arbiter", passed,
        detail,
        {
            "gate_summary": gate_summary,
            "failed_gates": failed_gates,
            "total_gates": len(gate_results),
            "passed_count": len(gate_results) - len(failed_gates),
        },
    )


# ============================================================================
# Pipeline Orchestrator
# ============================================================================

def run_verification_pipeline(
    api_key: str,
    candidate: dict,
    task_id: str,
    existing_ids: set,
    expected_topic: str,
    expected_subtopic: str,
    expected_level: str,
    existing_statements: Optional[List[str]] = None,
) -> dict:
    """Run all 13 verification gates on a candidate task.

    Args:
        api_key: DeepSeek API key.
        candidate: Task dict with keys statement, answer, solution.
        task_id: Unique task identifier.
        existing_ids: Set of already-used task IDs.
        expected_topic: Expected topic string.
        expected_subtopic: Expected subtopic string.
        expected_level: Expected level (L1/L2/L3).
        existing_statements: Optional list of existing task statements for dedup.

    Returns:
        Dict with keys: passed (bool), detail (str), gates (list of results),
                        pipeline_data (dict with all intermediate data).
    """
    if existing_statements is None:
        existing_statements = []

    statement = candidate.get("statement", "")
    answer = candidate.get("answer", "")
    solution = candidate.get("solution", "")

    # Collect all gate results
    gate_results = {}

    # GATE 1: Schema
    gate_results["schema"] = gate_schema(candidate)

    if not gate_results["schema"]["passed"]:
        return _build_pipeline_result(False, gate_results, "SCHEMA_FAILURE")

    # GATE 2: Uniqueness
    gate_results["uniqueness"] = gate_uniqueness(task_id, existing_ids)

    # GATE 3: Solver A
    gate_results["solver_a"] = gate_solver_a(api_key, statement)

    if not gate_results["solver_a"]["passed"]:
        return _build_pipeline_result(False, gate_results, "SOLVER_A_FAILURE")

    # GATE 4: Solver B
    gate_results["solver_b"] = gate_solver_b(api_key, statement)

    if not gate_results["solver_b"]["passed"]:
        return _build_pipeline_result(False, gate_results, "SOLVER_B_FAILURE")

    # Extract solver answers/solutions for downstream gates
    solver_a_answer = gate_results["solver_a"].get("solver_answer", "")
    solver_b_answer = gate_results["solver_b"].get("solver_answer", "")
    solver_a_solution = gate_results["solver_a"].get("solver_solution", "")
    solver_b_solution = gate_results["solver_b"].get("solver_solution", "")

    # GATE 5: Answer comparison
    gate_results["answer_compare"] = gate_answer_compare(
        answer, solver_a_answer, solver_b_answer,
    )

    # GATE 6: Solution verification
    gate_results["solution_verify"] = gate_solution_verify(
        solver_a_solution, solver_b_solution,
    )

    # GATE 7: Topic classification
    gate_results["topic_class"] = gate_topic_class(api_key, statement, expected_topic)

    # GATE 8: Subtopic classification
    gate_results["subtopic_class"] = gate_subtopic_class(api_key, statement, expected_subtopic)

    # GATE 9: Level classification
    gate_results["level_class"] = gate_level_class(api_key, statement, expected_level)

    # GATE 10: Level arbiter (only if level_class failed)
    if not gate_results["level_class"]["passed"]:
        gate_results["level_arbiter"] = gate_level_arbiter(api_key, statement, expected_level)
    else:
        gate_results["level_arbiter"] = _make_gate_result(
            "level_arbiter", True,
            "Skipped — level_class already passed",
            {"skipped": True},
        )

    # GATE 11: Exact duplicate check
    gate_results["exact_dup"] = gate_exact_dup(statement, existing_statements)

    # GATE 12: Template duplicate check
    gate_results["template_dup"] = gate_template_dup(statement, existing_statements)

    # GATE 13: Content arbiter (final verdict)
    gate_results["content_arbiter"] = gate_content_arbiter(gate_results)

    overall_pass = gate_results["content_arbiter"]["passed"]

    return _build_pipeline_result(
        overall_pass,
        gate_results,
        "ACCEPT" if overall_pass else "REJECT",
    )


def _build_pipeline_result(
    passed: bool,
    gate_results: Dict[str, dict],
    reason: str,
) -> dict:
    """Build the final pipeline result dict."""
    gates_list = []
    for gname, gres in gate_results.items():
        gates_list.append({
            "gate": gres.get("gate", gname),
            "passed": gres.get("passed", False),
            "detail": gres.get("detail", ""),
        })

    return {
        "passed": passed,
        "reason": reason,
        "gates": gates_list,
        "gate_details": gate_results,
        "pipeline_data": {
            "gate_count": len(gate_results),
            "passed_count": sum(1 for g in gates_list if g["passed"]),
            "failed_count": sum(1 for g in gates_list if not g["passed"]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
