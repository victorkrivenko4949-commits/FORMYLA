#!/usr/bin/env python
"""
Stage 5: Fix the 14 remaining FIX tasks (after Stage 4.5 reclassification).

For each FIX task:
1. Preserve condition and reference answer
2. Use AI to supplement/rewrite the solution to be complete and correct
3. Run independent SOLVER verification (deepseek-reasoner)
4. Compare solver answer with reference answer
5. If match -> FIXED (approved)
6. If not -> retry up to 3 cycles
7. If still failing after 3 cycles -> mark as REPLACE

Usage:
    set PYTHONIOENCODING=utf-8
    python _04_stage5_fix_tasks.py
"""

import json
import os
import sys
import re
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(WORK_DIR)
sys.path.insert(0, PROJECT_DIR)

AUDIT_PATH = os.path.join(WORK_DIR, "stage3_audit_results.json")
RECLASS_PATH = os.path.join(WORK_DIR, "stage45_reclassification.json")
OUTPUT_PATH = os.path.join(WORK_DIR, "stage5_fix_results.json")
REPORT_PATH = os.path.join(WORK_DIR, "stage5_fix_report.txt")
FIX_DIR = os.path.join(WORK_DIR, "stage5_fixes")
os.makedirs(FIX_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(WORK_DIR, "stage5_fix.log"), encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SOLVER prompt for verification (fixed LaTeX escaping)
# ---------------------------------------------------------------------------
SOLVER_SYSTEM_PROMPT = """Ты — независимый математик-решатель (SOLVER).
Твоя задача — решить математическую задачу и выдать ответ в строгом JSON-формате.

Верни ТОЛЬКО JSON-объект (без markdown-разметки, без лишнего текста):
{
  "solver_solution": "Полное, подробное, пошаговое решение на русском языке",
  "solver_answer": "Ответ (число, выражение или краткая фраза)",
  "solver_confidence": 0.0-1.0,
  "solver_notes": "Любые дополнительные замечания"
}

ВАЖНО: Используй \\( ... \\) для формул. Экранируй обратный слеш: вместо \\( пиши \\\\(, вместо \\) пиши \\\\), вместо \\. пиши \\\\. Это критически важно для корректного JSON."""

SOLVER_USER_PROMPT_TEMPLATE = """Реши следующую задачу. Выдай ответ строго в JSON-формате.

Условие: {statement}

Найди правильный ответ и запиши пошаговое решение."""

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def fix_latex_escapes(text: str) -> str:
    """Escape backslashes before parentheses so json.loads works."""
    text = text.replace('\\(', '\\\\(')
    text = text.replace('\\)', '\\\\)')
    text = text.replace('\\.', '\\\\.')
    return text


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Try to extract a JSON object from text, handling markdown fences and LaTeX escapes."""
    if not text or not text.strip():
        return None

    # Remove markdown fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Find first { after ```
        first_brace = cleaned.find("{")
        if first_brace >= 0:
            cleaned = cleaned[first_brace:]
        else:
            return None
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    # Remove trailing ``` if present
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    # Try as-is first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try with LaTeX escape fix
    fixed = fix_latex_escapes(cleaned)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object boundaries
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        candidate = cleaned[first_brace:last_brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        fixed_candidate = fix_latex_escapes(candidate)
        try:
            return json.loads(fixed_candidate)
        except json.JSONDecodeError:
            pass

    return None


def normalize_answer(ans: str) -> str:
    """Normalize answer for comparison: strip, lower, remove LaTeX, remove extra spaces."""
    if not ans:
        return ""
    ans = ans.strip()
    ans = ans.lower()
    # Remove LaTeX delimiters
    ans = ans.replace(r'\(', '')
    ans = ans.replace(r'\)', '')
    ans = ans.replace(r'\\', '')
    # Remove extra whitespace
    ans = re.sub(r'\s+', ' ', ans)
    return ans.strip()


def answers_match(solver_answer: str, reference_answer: str) -> bool:
    """Compare solver answer with reference answer, with normalization."""
    s = normalize_answer(solver_answer)
    r = normalize_answer(reference_answer)
    if not s or not r:
        return False
    # Direct string comparison
    if s == r:
        return True
    # Check if one contains the other
    if s in r or r in s:
        return True
    # Try numeric comparison
    try:
        s_num = float(s)
        r_num = float(r)
        if abs(s_num - r_num) < 1e-6:
            return True
    except (ValueError, TypeError):
        pass
    # Try to extract numbers from both
    s_nums = re.findall(r'-?\d+(?:\.\d+)?', s)
    r_nums = re.findall(r'-?\d+(?:\.\d+)?', r)
    if s_nums and r_nums and s_nums == r_nums:
        return True
    return False


def load_json(path: str, desc: str = "file") -> Any:
    """Load JSON file with utf-8 encoding."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any, desc: str = "file") -> None:
    """Save JSON file with utf-8 encoding."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Fix generation prompt
# ---------------------------------------------------------------------------
FIX_SYSTEM_PROMPT = """Ты — эксперт по математике, который дорабатывает решения задач.

Дана задача, её правильный ответ и текущее (неполное или некорректное) решение.

Твоя задача: написать ПОЛНОЕ, подробное, пошаговое решение, которое приводит к указанному правильному ответу.

Правила:
1. НЕ меняй условие задачи.
2. НЕ меняй правильный ответ.
3. Напиши полное математически строгое решение на русском языке.
4. Используй \\( ... \\) для формул. Экранируй обратный слеш: \\\\( ... \\\\)
5. Решение должно быть самодостаточным — любой ученик сможет его понять.
6. Верни ТОЛЬКО JSON:
{
  "fixed_solution": "Полное решение на русском языке",
  "changes": "Краткое описание, что было исправлено/добавлено"
}"""

FIX_USER_PROMPT_TEMPLATE = """Задача: {statement}

Правильный ответ: {reference_answer}

Текущее решение: {current_solution}

Напиши полное, подробное, пошаговое решение, которое приводит к ответу "{reference_answer}"."""


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def call_solver(client, statement: str) -> Dict[str, Any]:
    """Call deepseek-reasoner to solve a problem, return parsed result."""
    from ai.deepseek_client import DeepSeekClient
    if client is None:
        client = DeepSeekClient()
    
    prompt = SOLVER_USER_PROMPT_TEMPLATE.format(statement=statement)
    
    try:
        raw = client.generate_with_reasoning(
            prompt=prompt,
            system_prompt=SOLVER_SYSTEM_PROMPT,
            max_tokens=3000,
            timeout=300,
        )
        if not raw or not raw.strip():
            return {"status": "empty_response", "raw": "", "data": None}
        
        parsed = _extract_json(raw)
        if parsed is None:
            return {"status": "parse_failed", "raw": raw[:500], "data": None}
        
        return {
            "status": "ok",
            "raw": raw[:500],
            "data": {
                "solver_solution": parsed.get("solver_solution", ""),
                "solver_answer": parsed.get("solver_answer", ""),
                "solver_confidence": parsed.get("solver_confidence", 0),
                "solver_notes": parsed.get("solver_notes", ""),
            }
        }
    except Exception as e:
        return {"status": "error", "raw": str(e)[:500], "data": None}


def fix_task(client, statement: str, reference_answer: str, current_solution: str) -> Optional[str]:
    """Use AI to fix the solution for a task. Returns fixed_solution or None."""
    from ai.deepseek_client import DeepSeekClient
    if client is None:
        client = DeepSeekClient()
    
    prompt = FIX_USER_PROMPT_TEMPLATE.format(
        statement=statement,
        reference_answer=reference_answer,
        current_solution=current_solution
    )
    
    try:
        raw = client.generate(
            prompt=prompt,
            system_prompt=FIX_SYSTEM_PROMPT,
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        if not raw:
            log.warning("  Fix generation returned empty response")
            return None
        
        parsed = _extract_json(raw)
        if parsed is None:
            log.warning("  Fix generation: could not parse JSON response")
            return None
        
        fixed_solution = parsed.get("fixed_solution", "")
        if not fixed_solution:
            log.warning("  Fix generation: empty fixed_solution")
            return None
        
        return fixed_solution
    except Exception as e:
        log.warning(f"  Fix generation error: {e}")
        return None


def main():
    from ai.deepseek_client import DeepSeekClient
    
    log.info("=" * 60)
    log.info("STAGE 5: FIX TASKS")
    log.info("=" * 60)
    
    # Load data
    audit_results = load_json(AUDIT_PATH, "audit results")
    reclass_data = load_json(RECLASS_PATH, "reclassification data")
    
    # Build lookup: task_id -> audit entry
    audit_lookup = {entry["task_id"]: entry for entry in audit_results}
    
    # Get FIX tasks from reclassification
    fix_tasks = [
        r for r in reclass_data["reclassifications"]
        if r["new_category"] == "FIX"
    ]
    log.info(f"Found {len(fix_tasks)} FIX tasks to process")
    
    # Initialize client
    client = DeepSeekClient()
    log.info("DeepSeekClient initialized")
    
    results = []
    stats = {"fixed": 0, "replace": 0, "error": 0}
    
    for idx, task in enumerate(fix_tasks, 1):
        task_id = task["task_id"]
        cell_key = task["cell_key"]
        statement = task["statement"]
        reference_answer = task["reference_answer"]
        solver_answer = task.get("solver_answer", "")
        q_score = task["quality_score"]
        
        log.info(f"\n[{idx}/{len(fix_tasks)}] Task {task_id} | {cell_key} | q={q_score}")
        log.info(f"  Statement: {statement[:80]}...")
        log.info(f"  Reference: {reference_answer}")
        log.info(f"  Solver had: {solver_answer}")
        
        # Get original solution from audit data
        audit_entry = audit_lookup.get(task_id, {})
        current_solution = audit_entry.get("solution", "")
        log.info(f"  Current solution length: {len(current_solution)} chars")
        
        fix_cycle_log = []
        final_solution = None
        final_result = None
        outcome = "error"
        
        for cycle in range(1, 4):  # Max 3 cycles
            log.info(f"  --- Cycle {cycle}/3 ---")
            
            # Step 1: Generate fixed solution
            log.info(f"  Fixing solution...")
            fixed_solution = fix_task(client, statement, reference_answer, current_solution)
            
            if fixed_solution is None:
                log.warning(f"  Fix generation failed, retrying...")
                cycle_log_entry = {
                    "cycle": cycle,
                    "fix_status": "failed",
                    "solver_status": "skipped",
                }
                fix_cycle_log.append(cycle_log_entry)
                continue
            
            log.info(f"  Fixed solution length: {len(fixed_solution)} chars")
            
            # Step 2: Verify with SOLVER (blind solve)
            log.info(f"  Verifying with SOLVER...")
            solver_result = call_solver(client, statement)
            
            solver_ok = solver_result["status"] == "ok"
            solver_answer_verified = ""
            answer_matches = False
            
            if solver_ok and solver_result["data"]:
                solver_answer_verified = solver_result["data"].get("solver_answer", "")
                answer_matches = answers_match(solver_answer_verified, reference_answer)
                log.info(f"  SOLVER answered: {solver_answer_verified}")
                log.info(f"  Answer matches reference: {answer_matches}")
            else:
                log.warning(f"  SOLVER status: {solver_result['status']}")
            
            cycle_log_entry = {
                "cycle": cycle,
                "fix_status": "ok" if fixed_solution else "failed",
                "fixed_solution": fixed_solution,
                "solver_status": solver_result["status"],
                "solver_answer": solver_answer_verified,
                "answer_matches": answer_matches,
            }
            fix_cycle_log.append(cycle_log_entry)
            
            if answer_matches:
                outcome = "fixed"
                final_solution = fixed_solution
                final_result = solver_result
                log.info(f"  [OK] Cycle {cycle}: FIXED!")
                break
            else:
                log.info(f"  Cycle {cycle}: answer still doesn't match. Trying again...")
                # Use the fixed solution as current for next cycle
                current_solution = fixed_solution
        
        if outcome != "fixed":
            outcome = "replace"
            log.warning(f"   After 3 cycles, still not matching. Marking as REPLACE.")
        
        result_entry = {
            "task_id": task_id,
            "cell_key": cell_key,
            "quality_score": q_score,
            "statement": statement,
            "reference_answer": reference_answer,
            "outcome": outcome,
            "final_solution": final_solution,
            "cycles": fix_cycle_log,
        }
        results.append(result_entry)
        stats[outcome] = stats.get(outcome, 0) + 1
        
        # Save per-task forensic log
        forensic_path = os.path.join(FIX_DIR, f"{task_id}_fix_log.json")
        save_json(forensic_path, result_entry, f"fix log for {task_id}")
        
        brief = "FIXED" if outcome == "fixed" else "REPLACE"
        log.info(f"  >>> {brief}")
    
    # Summary
    log.info("\n" + "=" * 60)
    log.info("STAGE 5 COMPLETE")
    log.info(f"  Fixed: {stats.get('fixed', 0)}")
    log.info(f"  Replace: {stats.get('replace', 0)}")
    log.info(f"  Error: {stats.get('error', 0)}")
    log.info("=" * 60)
    
    # Save results
    output = {
        "summary": {
            "total_fix_tasks": len(fix_tasks),
            "fixed": stats.get("fixed", 0),
            "replace": stats.get("replace", 0),
            "error": stats.get("error", 0),
        },
        "results": results,
    }
    save_json(OUTPUT_PATH, output, "stage 5 results")
    
    # Generate report
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("  STAGE 5: FIX RESULTS REPORT\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"  Total FIX tasks: {len(fix_tasks)}\n")
        f.write(f"  Fixed: {stats.get('fixed', 0)}\n")
        f.write(f"  Replace: {stats.get('replace', 0)}\n")
        f.write(f"  Error: {stats.get('error', 0)}\n\n")
        f.write("-" * 70 + "\n")
        f.write(f"  {'ID':<20} {'Cell':<25} {'Q':<6} {'Outcome':<10}\n")
        f.write("-" * 70 + "\n")
        for r in results:
            outcome_tag = "FIXED" if r["outcome"] == "fixed" else "REPLACE"
            f.write(f"  {r['task_id']:<20} {r['cell_key']:<25} {r['quality_score']:<6.1f} {outcome_tag:<10}\n")
        f.write("\n" + "=" * 70 + "\n")
        f.write("  END OF STAGE 5 REPORT\n")
        f.write("=" * 70 + "\n")
    
    log.info(f"Report saved to {REPORT_PATH}")
    log.info(f"Results saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
