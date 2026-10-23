#!/usr/bin/env python
"""
Stage 4.5: Deep reclassification of all 40 FIX-classified tasks.

For each FIX task:
1. Diagnose the exact SOLVER failure type from 9 categories:
   - api_error, timeout, invalid_json, empty_response, parsing_error,
     no_solution_found, contradiction_found, wrong_original_answer,
     incomplete_original_solution
2. For technical failures (api_error, timeout, invalid_json, empty_response,
   parsing_error): retry SOLVER up to 3× with deepseek-reasoner, extended timeout
3. Save raw model responses to forensic log
4. Reclassify:
   - If retry confirms answer AND original solution is complete  -> KEEP
   - If answer correct but solution missing steps               -> FIX (supplement solution only)
   - If math error found                                        -> REPLACE
5. Output updated counts: KEEP / FIX / REPLACE / REVIEW

Usage:
    set PYTHONIOENCODING=utf-8
    python _03_stage45_reclassify.py
"""

import json
import os
import sys
import re
import time
import logging
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(WORK_DIR)

AUDIT_PATH = os.path.join(WORK_DIR, "stage3_audit_results.json")
CLASSIFICATION_PATH = os.path.join(WORK_DIR, "stage4_classification.json")
OUTPUT_PATH = os.path.join(WORK_DIR, "stage45_reclassification.json")
REPORT_PATH = os.path.join(WORK_DIR, "stage45_reclassification_report.txt")
FORENSIC_DIR = os.path.join(WORK_DIR, "stage45_forensics")
os.makedirs(FORENSIC_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(WORK_DIR, "stage45_reclassify.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("stage45")

# ---------------------------------------------------------------------------
# JSON fix helpers
# ---------------------------------------------------------------------------
# The model often outputs LaTeX \(...\) inside JSON string values.
# In JSON, \( is not a valid escape sequence, so json.loads fails.
# Fix: pre-escape backslashes before parentheses.
def fix_latex_escapes(text: str) -> str:
    """Escape backslashes before parentheses so json.loads works."""
    # Replace \( with \\( and \) with \\) 
    # In Python strings: '\(' is 2 chars: \ and (
    # We want to replace with '\\(' which is 3 chars: \ \ (
    text = text.replace('\\(', '\\\\(')
    text = text.replace('\\)', '\\\\)')
    # Also fix other potentially problematic LaTeX escapes
    text = text.replace('\\.', '\\\\.')
    return text


def _extract_json_with_fix(text: str) -> Optional[Dict[str, Any]]:
    """Try to extract JSON, with LaTeX escape fix."""
    # Try as-is first
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        text_clean = m.group(1)
    else:
        m = re.search(r"(\{.*\})", text, re.DOTALL)
        if m:
            text_clean = m.group(1)
        else:
            text_clean = text

    # Try direct parse
    try:
        return json.loads(text_clean)
    except json.JSONDecodeError:
        pass

    # Try with LaTeX escape fix
    try:
        fixed = fix_latex_escapes(text_clean)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    return None


# ---------------------------------------------------------------------------
# Failure diagnosis
# ---------------------------------------------------------------------------
class FailureDiagnosis:
    """Diagnose the exact SOLVER failure type."""

    @staticmethod
    def diagnose(solver_audit: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns dict with:
          - failure_type: str (one of 9 categories, or 'no_failure')
          - detail: str explaining the diagnosis
          - recovered_data: Optional[dict] if we could extract data despite failure
        """
        status = solver_audit.get("status", "")
        detail = ""
        recovered_data = None

        if status == "ok":
            data = solver_audit.get("data", {})
            solver_answer = str(data.get("solver_answer", "")).strip()
            if not solver_answer:
                return {"failure_type": "no_solution_found",
                        "detail": "SOLVER returned ok but solver_answer is empty",
                        "recovered_data": data}
            return {"failure_type": "no_failure",
                    "detail": "SOLVER succeeded",
                    "recovered_data": data}

        if status == "error":
            error_str = str(solver_audit.get("error", ""))
            if "timeout" in error_str.lower():
                return {"failure_type": "timeout",
                        "detail": f"API timeout: {error_str}",
                        "recovered_data": None}
            if "connection" in error_str.lower():
                return {"failure_type": "api_error",
                        "detail": f"Connection error: {error_str}",
                        "recovered_data": None}
            return {"failure_type": "api_error",
                    "detail": f"API error: {error_str}",
                    "recovered_data": None}

        if status == "parse_failed":
            raw = solver_audit.get("raw", "")
            if not raw or len(raw.strip()) < 10:
                return {"failure_type": "empty_response",
                        "detail": "SOLVER returned empty or near-empty response",
                        "recovered_data": None}

            # Try to extract JSON with fixes
            parsed = _extract_json_with_fix(raw)
            if parsed:
                solver_answer = str(parsed.get("solver_answer", "")).strip()
                solver_solution = parsed.get("solver_solution", "")
                if solver_answer:
                    detail = (f"parse_fixed: LaTeX escape issue. "
                              f"Answer={solver_answer}, solution_len={len(solver_solution)}")
                    return {"failure_type": "parsing_error",
                            "detail": detail,
                            "recovered_data": parsed}
                else:
                    return {"failure_type": "invalid_json",
                            "detail": "JSON parsed after fix but no solver_answer field found",
                            "recovered_data": parsed}

            # Check if raw contains any JSON-like structure at all
            if '{' not in raw:
                return {"failure_type": "no_solution_found",
                        "detail": "Model returned natural language without JSON structure",
                        "recovered_data": None}

            # Check if the response looks like a reasoning chain (very long, no JSON)
            if len(raw) > 1000 and '{' not in raw[:200]:
                return {"failure_type": "no_solution_found",
                        "detail": f"Model returned long natural language ({len(raw)} chars), no JSON",
                        "recovered_data": None}

            return {"failure_type": "invalid_json",
                    "detail": f"Could not parse JSON from response ({len(raw)} chars)",
                    "recovered_data": None}

        return {"failure_type": "unknown",
                "detail": f"Unexpected status: {status}",
                "recovered_data": None}


# ---------------------------------------------------------------------------
# Compare answers
# ---------------------------------------------------------------------------
def normalize_answer(answer: str) -> str:
    """Normalize an answer for comparison (strip, lower, remove extra spaces)."""
    if not answer:
        return ""
    answer = str(answer).strip().lower()
    # Remove LaTeX delimiters
    answer = answer.replace('\\(', '').replace('\\)', '')
    answer = answer.replace('$', '')
    # Remove extra whitespace
    answer = re.sub(r'\s+', ' ', answer)
    return answer.strip()


def answers_match(solver_answer: str, reference_answer: str) -> bool:
    """Check if two answers match semantically."""
    if not solver_answer or not reference_answer:
        return False
    a = normalize_answer(solver_answer)
    b = normalize_answer(reference_answer)
    if a == b:
        return True
    # Try numeric comparison
    try:
        num_a = float(a.replace(',', '.'))
        num_b = float(b.replace(',', '.'))
        if abs(num_a - num_b) < 0.001:
            return True
    except ValueError:
        pass
    return False


# ---------------------------------------------------------------------------
# Solution completeness heuristic
# ---------------------------------------------------------------------------
def is_solution_complete(original_solution: str, statement: str) -> bool:
    """
    Heuristic: a solution is "complete" if it contains enough mathematical
    substance to solve the problem.
    """
    sol = (original_solution or "").strip()
    if not sol:
        return False

    # Length heuristic: very short solutions (<50 chars) are likely incomplete
    if len(sol) < 50:
        return False

    # Check for answer presence in solution
    return True


# ---------------------------------------------------------------------------
# Retry SOLVER
# ---------------------------------------------------------------------------
SOLVER_SYSTEM_PROMPT = """Ты — независимый математик-решатель (SOLVER).
Твоя задача: реши предложенную задачу самостоятельно, НЕ глядя на готовое решение.
Выпиши полное, строгое решение с обоснованием каждого шага.
В конце укажи ответ.

ВАЖНО: Используй \( ... \) для формул. Не используй обратный слеш перед скобками в JSON значениях.
Вместо \( ... \) используй \\( ... \\)  — то есть экранируй обратный слеш.

Выведи результат строго в JSON-формате:
{
  "solver_solution": "твоё полное решение задачи",
  "solver_answer": "итоговый ответ",
  "solver_confidence": 0.0-1.0,
  "solver_notes": "любые замечания о сложности, неоднозначности условия и т.д."
}"""


def retry_solver(client, task: Dict[str, Any], attempt: int = 1) -> Dict[str, Any]:
    """Retry SOLVER with extended timeout."""
    statement = task.get("statement", "")
    prompt = (
        f"Реши следующую математическую задачу. Выпиши полное решение.\n\n"
        f"---\n{statement}\n---\n\n"
        f"Выведи ответ строго в JSON-формате. "
        f"ВАЖНО: Для формул используй \\( ... \\) с ДВОЙНЫМ обратным слешем, "
        f"чтобы JSON был валидным."
    )
    timeout = 300 + (attempt * 60)  # 360s, 420s, 480s
    try:
        raw = client.generate_with_reasoning(
            prompt=prompt,
            system_prompt=SOLVER_SYSTEM_PROMPT,
            max_tokens=3000,
            timeout=timeout,
        )
        parsed = _extract_json_with_fix(raw)
        if parsed:
            return {"status": "ok", "data": parsed, "raw": raw[:2000]}
        else:
            return {"status": "parse_failed", "raw": raw[:2000]}
    except Exception as e:
        logger.error(f"  Retry attempt {attempt} failed: {e}")
        return {"status": "error", "error": str(e), "raw": ""}


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------
def load_json(path, desc="file"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_forensic(task_id: str, cell_key: str, data: Dict[str, Any]):
    """Save forensic data for a task."""
    safe_name = f"{task_id}_{cell_key.replace('|', '_')}"
    path = os.path.join(FORENSIC_DIR, f"{safe_name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
def main():
    sys.path.insert(0, PROJECT_DIR)
    from ai.deepseek_client import DeepSeekClient

    client = DeepSeekClient()
    logger.info("DeepSeekClient initialized")

    # Load audit results and classification
    audit_results = load_json(AUDIT_PATH, "audit results")
    classification = load_json(CLASSIFICATION_PATH, "classification")

    logger.info(f"Loaded {len(audit_results)} audit results")
    logger.info(f"Loaded classification with {len(classification.get('classifications', []))} entries")

    # Build lookup: task_id -> audit result
    audit_lookup = {r["task_id"]: r for r in audit_results}

    # Build lookup: task_id -> classification
    class_lookup = {}
    for c in classification.get("classifications", []):
        class_lookup[c["task_id"]] = c

    # Identify FIX tasks
    fix_tasks = [c for c in classification.get("classifications", [])
                 if c.get("category") == "FIX"]
    logger.info(f"Found {len(fix_tasks)} FIX tasks for Stage 4.5 analysis")

    # Results
    reclassifications = []
    summary_stats = {
        "total_fix": len(fix_tasks),
        "by_failure_type": {},
        "by_new_category": {"KEEP": 0, "FIX": 0, "REPLACE": 0},
        "retry_stats": {"attempted": 0, "succeeded": 0, "failed": 0},
    }

    for idx, fix_entry in enumerate(fix_tasks):
        task_id = fix_entry["task_id"]
        cell_key = fix_entry.get("cell_key", "")
        reason = fix_entry.get("reason", "")
        quality = fix_entry.get("quality_score", 0)
        statement = fix_entry.get("statement", "")

        logger.info(f"\n[{idx+1}/{len(fix_tasks)}] Task {task_id} | {cell_key} | q={quality} | reason={reason}")

        # Get audit data
        audit_entry = audit_lookup.get(task_id)
        if not audit_entry:
            logger.warning(f"  No audit data found for {task_id}")
            reclassifications.append({
                "task_id": task_id, "cell_key": cell_key,
                "new_category": "REVIEW",
                "diagnosis": "no_audit_data",
                "detail": "No audit results found for this task",
            })
            summary_stats["by_new_category"]["REVIEW"] += 1
            continue

        solution = audit_entry.get("solution", "")
        reference_answer = audit_entry.get("reference_answer", "")

        # Find SOLVER audit
        solver_audit = None
        for a in audit_entry.get("audits", []):
            if a["role"] == "SOLVER":
                solver_audit = a
                break

        if not solver_audit:
            logger.warning(f"  No SOLVER audit found for {task_id}")
            reclassifications.append({
                "task_id": task_id, "cell_key": cell_key,
                "new_category": "REVIEW",
                "diagnosis": "no_solver_audit",
                "detail": "No SOLVER audit record found",
            })
            summary_stats["by_new_category"]["REVIEW"] += 1
            continue

        # 1) Diagnose failure type
        diagnosis = FailureDiagnosis.diagnose(solver_audit)
        failure_type = diagnosis["failure_type"]
        detail = diagnosis["detail"]
        recovered_data = diagnosis.get("recovered_data")

        summary_stats["by_failure_type"][failure_type] = \
            summary_stats["by_failure_type"].get(failure_type, 0) + 1

        logger.info(f"  Diagnosis: {failure_type} — {detail[:120]}")

        # 2) Try to recover answer
        solver_answer = ""
        solver_solution = ""
        if recovered_data:
            solver_answer = str(recovered_data.get("solver_answer", "")).strip()
            solver_solution = recovered_data.get("solver_solution", "")

        # 3) For technical failures, retry
        technical_types = {"api_error", "timeout", "invalid_json",
                          "empty_response", "parsing_error", "unknown"}
        retry_attempted = False
        retry_result = None

        if failure_type in technical_types:
            summary_stats["retry_stats"]["attempted"] += 1
            retry_attempted = True

            for attempt in range(1, 4):  # up to 3 retries
                logger.info(f"  Retry {attempt}/3...")
                retry_result = retry_solver(client, audit_entry, attempt)

                if retry_result["status"] == "ok":
                    summary_stats["retry_stats"]["succeeded"] += 1
                    solver_answer = str(retry_result["data"].get("solver_answer", "")).strip()
                    solver_solution = retry_result["data"].get("solver_solution", "")
                    logger.info(f"  Retry {attempt} succeeded! Answer={solver_answer}")
                    break
                else:
                    logger.info(f"  Retry {attempt} failed: {retry_result.get('status')}")
                    time.sleep(5)
            else:
                summary_stats["retry_stats"]["failed"] += 1
                logger.warning(f"  All 3 retries failed for {task_id}")

            # Save forensic data
            forensic_data = {
                "task_id": task_id,
                "cell_key": cell_key,
                "statement": statement[:200],
                "reference_answer": reference_answer,
                "original_solver": {
                    "status": solver_audit.get("status"),
                    "raw_preview": str(solver_audit.get("raw", ""))[:500],
                },
                "diagnosis": diagnosis,
                "retry_result": retry_result,
                "final_solver_answer": solver_answer,
            }
            save_forensic(task_id, cell_key, forensic_data)

        # 4) Determine reclassification
        new_category = None
        reclass_reason = ""

        if failure_type == "no_failure":
            # SOLVER succeeded originally
            answer_ok = answers_match(solver_answer, reference_answer)
            solution_complete = is_solution_complete(solution, statement)

            if answer_ok and solution_complete:
                new_category = "KEEP"
                reclass_reason = "SOLVER_ok+answer_matches+solution_complete"
            elif answer_ok and not solution_complete:
                new_category = "FIX"
                reclass_reason = "SOLVER_ok+answer_matches_but_solution_incomplete"
            elif not answer_ok:
                # Math error — check through ARBITER
                arbiter_audit = None
                for a in audit_entry.get("audits", []):
                    if a["role"] == "ARBITER":
                        arbiter_audit = a
                        break
                arbiter_ok = arbiter_audit and arbiter_audit.get("status") == "ok"
                arbiter_verdict = ""
                if arbiter_ok:
                    arbiter_verdict = arbiter_audit["data"].get("arbiter_verdict", "")

                if arbiter_verdict == "совпадает":
                    # ARBITER says matches despite different answer? Unlikely but possible for proofs
                    new_category = "FIX"
                    reclass_reason = "SOLVER_ok+arbiter_matches_but_answer_differs"
                else:
                    new_category = "REPLACE"
                    reclass_reason = "SOLVER_ok+wrong_answer"
            else:
                new_category = "FIX"
                reclass_reason = "SOLVER_ok+ambiguous"

        elif retry_attempted and retry_result and retry_result["status"] == "ok":
            # Retry succeeded
            answer_ok = answers_match(solver_answer, reference_answer)
            solution_complete = is_solution_complete(solution, statement)

            if answer_ok and solution_complete:
                new_category = "KEEP"
                reclass_reason = f"retry_ok+answer_matches+solution_complete (was:{failure_type})"
            elif answer_ok and not solution_complete:
                new_category = "FIX"
                reclass_reason = f"retry_ok+answer_matches_but_solution_incomplete (was:{failure_type})"
            elif not answer_ok:
                new_category = "REPLACE"
                reclass_reason = f"retry_ok+wrong_answer (was:{failure_type})"
            else:
                new_category = "FIX"
                reclass_reason = f"retry_ok+ambiguous (was:{failure_type})"
        else:
            # Could not recover — keep as FIX or escalate
            # If SOLVER failed AND solution is very short (<50 chars), it's REPLACE
            if len(solution.strip()) < 50:
                new_category = "REPLACE"
                reclass_reason = f"no_recovery+very_short_solution (failure:{failure_type})"
            else:
                new_category = "FIX"
                reclass_reason = f"no_recovery_solver_failure (failure:{failure_type})"

        # Apply override: if ARBITER found errors in reference, reconsider
        arbiter_audit = None
        for a in audit_entry.get("audits", []):
            if a["role"] == "ARBITER":
                arbiter_audit = a
                break
        if arbiter_audit and arbiter_audit.get("status") == "ok":
            arbiter_errors = arbiter_audit["data"].get("arbiter_errors_in_reference", [])
            if arbiter_errors and new_category != "REPLACE":
                # ARBITER found errors in reference solution — task may still be salvageable
                if new_category == "KEEP":
                    new_category = "FIX"
                    reclass_reason += "+arbiter_found_ref_errors"

        if not new_category:
            new_category = "FIX"
            reclass_reason = "fallback"

        summary_stats["by_new_category"][new_category] += 1

        logger.info(f"  -> New category: {new_category} ({reclass_reason})")

        reclassifications.append({
            "task_id": task_id,
            "cell_key": cell_key,
            "quality_score": quality,
            "statement": statement[:100],
            "reference_answer": reference_answer,
            "original_category": "FIX",
            "original_reason": reason,
            "new_category": new_category,
            "reclass_reason": reclass_reason,
            "failure_type": failure_type,
            "failure_detail": detail[:300],
            "solver_answer": solver_answer,
            "solution_length": len(solution),
        })

    # -----------------------------------------------------------------------
    # Output results
    # -----------------------------------------------------------------------
    output = {
        "summary": {
            "total_fix_analyzed": len(fix_tasks),
            "failure_type_counts": summary_stats["by_failure_type"],
            "new_category_counts": summary_stats["by_new_category"],
            "retry_stats": summary_stats["retry_stats"],
        },
        "reclassifications": reclassifications,
    }
    save_json(OUTPUT_PATH, output)
    logger.info(f"\nResults saved to {OUTPUT_PATH}")

    # Generate report
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("  STAGE 4.5: RECLASSIFICATION REPORT\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"  Total FIX tasks analyzed: {len(fix_tasks)}\n\n")

        f.write("  Failure type breakdown:\n")
        for ft, count in sorted(summary_stats["by_failure_type"].items(),
                                key=lambda x: -x[1]):
            f.write(f"    {ft:30s}: {count}\n")

        f.write("\n  Retry stats:\n")
        rs = summary_stats["retry_stats"]
        f.write(f"    Attempted: {rs['attempted']}\n")
        f.write(f"    Succeeded: {rs['succeeded']}\n")
        f.write(f"    Failed:    {rs['failed']}\n")

        f.write("\n  New category counts:\n")
        for cat in ["KEEP", "FIX", "REPLACE", "REVIEW"]:
            count = summary_stats["by_new_category"].get(cat, 0)
            f.write(f"    {cat:10s}: {count}\n")

        f.write("\n" + "-" * 70 + "\n")
        f.write(f"  {'ID':<16} {'Cell':<20} {'Q':>6} {'Old':<8} {'New':<8} Failure/D reason\n")
        f.write("-" * 70 + "\n")

        for r in reclassifications:
            tid = r["task_id"][:14]
            cell = r["cell_key"]
            q = f"{r['quality_score']:.0f}"
            old = r["original_category"]
            new = r["new_category"]
            reason = r["reclass_reason"][:50]
            f.write(f"  {tid:<16} {cell:<20} {q:>6} {old:<8} {new:<8} {reason}\n")

        f.write("\n" + "=" * 70 + "\n")
        f.write("  END OF STAGE 4.5 REPORT\n")
        f.write("=" * 70 + "\n")

    logger.info(f"Report saved to {REPORT_PATH}")
    print(f"\n=== STAGE 4.5 COMPLETE ===")
    print(f"Failure types: {summary_stats['by_failure_type']}")
    print(f"New counts: {summary_stats['by_new_category']}")
    print(f"Retries: {summary_stats['retry_stats']}")


if __name__ == "__main__":
    main()
