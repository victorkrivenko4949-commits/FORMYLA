#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fix truncated _verification_gates.py by reading lines 1-610
and appending the complete remaining content.
"""
import os

SRC = r"l1_l3_generation\_verification_gates.py"

# Read existing content, keep first 610 lines
with open(SRC, "r", encoding="utf-8") as f:
    lines = f.readlines()

print(f"Original file: {len(lines)} lines")

# Keep only lines 1-610 (0-indexed: 0-609)
keep = lines[:610]
print(f"Keeping first 610 lines")

# ============================================================
# Remaining content to append
# NOTE: The original file had line 611 = '            "content": ('
# which was at index 610 and NOT included in lines[:610]
# ============================================================

remaining = r'''            "content": (
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
        detail = "ALL 13 GATES PASSED -> ACCEPT"
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
        "pipeline_data": {
            "gate_count": len(gate_results),
            "passed_count": sum(1 for g in gates_list if g["passed"]),
            "failed_count": sum(1 for g in gates_list if not g["passed"]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
'''


# Write the fixed file
with open(SRC, "w", encoding="utf-8") as f:
    f.writelines(keep)
    f.write(remaining)

print(f"Written fixed file. Checking line count...")

# Verify
with open(SRC, "r", encoding="utf-8") as f:
    new_lines = f.readlines()

print(f"New file: {len(new_lines)} lines")

# Quick syntax check
try:
    compile("".join(new_lines), SRC, "exec")
    print("SYNTAX CHECK: PASSED")
except SyntaxError as e:
    print(f"SYNTAX CHECK: FAILED — {e}")
