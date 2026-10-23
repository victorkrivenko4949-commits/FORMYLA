#!/usr/bin/env python
"""
Stage 4: Classify each audited task as KEEP / FIX / REPLACE / REVIEW.

Rules engine that consumes stage3_audit_results.json and produces
stage4_classification.json + stage4_classification_report.txt.

Classification logic:
  KEEP    — SOLVER succeeded ∧ ARBITER совпадает ∧ LEVEL matches expected ∧ unique
  FIX     — SOLVER succeeded but ARBITER has minor discrepancies, or level mismatch
  REPLACE — SOLVER failed ∧ critically short solution, or ARBITER major errors, or duplicate
  REVIEW  — borderline / insufficient data
"""

import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
AUDIT_PATH = BASE / "stage3_audit_results.json"
CLASS_PATH = BASE / "stage4_classification.json"
REPORT_PATH = BASE / "stage4_classification_report.txt"

# Expected levels per cell pattern (heuristic)
# L4 = levels 3-4, L5 = levels 4-5
EXPECTED_LEVEL_RANGES = {
    "L4": {3, 4},
    "L5": {4, 5},
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── helpers ──────────────────────────────────────────────────────────

def _get_audit(task, role):
    """Return audit dict for given role, or None."""
    for a in task.get("audits", []):
        if a["role"] == role:
            return a
    return None


def _audit_ok(audit):
    """True if role returned status == 'ok'."""
    return audit is not None and audit.get("status") == "ok"


def _solver_ok(task):
    a = _get_audit(task, "SOLVER")
    return _audit_ok(a)


def _arbiter_verdict(task):
    a = _get_audit(task, "ARBITER")
    if not _audit_ok(a):
        return None
    return a["data"].get("arbiter_verdict")


def _arbiter_discrepancies(task):
    a = _get_audit(task, "ARBITER")
    if not _audit_ok(a):
        return []
    return a["data"].get("arbiter_discrepancies", [])


def _arbiter_errors(task):
    a = _get_audit(task, "ARBITER")
    if not _audit_ok(a):
        return []
    return a["data"].get("arbiter_errors_in_reference", [])


def _predicted_level(task):
    a = _get_audit(task, "LEVEL_CALIBRATOR")
    if not _audit_ok(a):
        return None
    return a["data"].get("predicted_level")


def _is_duplicate(task):
    a = _get_audit(task, "DUPLICATE_JUDGE")
    if not _audit_ok(a):
        return False
    return a["data"].get("is_duplicate", False)


def _get_classifier_conf(task):
    a = _get_audit(task, "TOPIC_CLASSIFIER")
    if not _audit_ok(a):
        return 0.0
    return a["data"].get("confidence", 0.0)


def _solution_length(task):
    sol = task.get("solution", "")
    return len(sol)


def _expected_level(task):
    """Return set of expected levels based on task['level'] (which is L4 or L5)."""
    level_str = str(task.get("level", ""))
    if level_str in EXPECTED_LEVEL_RANGES:
        return EXPECTED_LEVEL_RANGES[level_str]
    return {3, 4, 5}  # fallback


# ── classifier ───────────────────────────────────────────────────────

VERY_SHORT_SOLUTION = 100       # chars
SHORT_SOLUTION = 300            # chars


def classify(task):
    """
    Return (category, reason) tuple.
    """
    q = task.get("quality_score", 0)
    sol_len = _solution_length(task)
    solver_ok = _solver_ok(task)
    verdict = _arbiter_verdict(task)
    discrepancies = _arbiter_discrepancies(task)
    errors = _arbiter_errors(task)
    pred_level = _predicted_level(task)
    expected_levels = _expected_level(task)
    is_dup = _is_duplicate(task)
    classifier_conf = _get_classifier_conf(task)

    reasons = []

    # ── REPLACE candidates ──
    if is_dup:
        return "REPLACE", "duplicate_detected"

    if not solver_ok and sol_len < VERY_SHORT_SOLUTION:
        return "REPLACE", "solver_failed_very_short_solution"

    if verdict == "не совпадает" or verdict == "частично совпадает":
        if len(errors) > 0:
            return "REPLACE", f"arbiter_errors:{'; '.join(errors[:3])}"

    if not solver_ok and q < 50:
        return "REPLACE", "solver_failed_low_quality"

    # ── FIX candidates ──
    if solver_ok and verdict in ("не совпадает", "частично совпадает"):
        reasons.append(f"arbiter:{verdict}")
        if len(reasons) > 0:
            return "FIX", "; ".join(reasons)

    if pred_level is not None and pred_level not in expected_levels:
        reasons.append(f"level_mismatch:predicted={pred_level},expected={expected_levels}")

    if not solver_ok:
        reasons.append("solver_failed")

    if sol_len < SHORT_SOLUTION:
        reasons.append(f"short_solution:{sol_len}chars")

    if classifier_conf < 0.5:
        reasons.append(f"low_topic_confidence:{classifier_conf}")

    if verdict == "частично совпадает":
        reasons.append(f"arbiter:{verdict}")

    if reasons:
        return "FIX", "; ".join(reasons)

    # ── KEEP ──
    if solver_ok and verdict == "совпадает":
        return "KEEP", "all_roles_ok"

    if q >= 68 and solver_ok:
        return "KEEP", "high_quality_solver_ok"

    # ── REVIEW (borderline) ──
    return "REVIEW", "insufficient_data_for_verdict"


# ── main ─────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  Stage 4: Classify audited tasks (KEEP / FIX / REPLACE / REVIEW)")
    print("=" * 70)

    if not AUDIT_PATH.exists():
        print(f"[ERROR] Audit results not found: {AUDIT_PATH}")
        sys.exit(1)

    audit_results = load_json(AUDIT_PATH)
    print(f"  Loaded {len(audit_results)} audit results\n")

    classified = []
    counts = {"KEEP": 0, "FIX": 0, "REPLACE": 0, "REVIEW": 0}

    for task in audit_results:
        cat, reason = classify(task)
        entry = {
            "task_id": task["task_id"],
            "cell_key": task["cell_key"],
            "quality_score": task["quality_score"],
            "phase": task["phase"],
            "statement": task.get("statement", "")[:100],
            "category": cat,
            "reason": reason,
        }
        classified.append(entry)
        counts[cat] = counts.get(cat, 0) + 1

    # Save JSON
    save_json(CLASS_PATH, {
        "summary": {
            "total": len(classified),
            "counts": counts,
        },
        "classifications": classified,
    })
    print(f"  Saved {CLASS_PATH}")

    # ── report ──
    lines = []
    lines.append("=" * 70)
    lines.append("  STAGE 4: CLASSIFICATION REPORT")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"  Total classified: {len(classified)}")
    lines.append(f"  KEEP    : {counts.get('KEEP', 0)}")
    lines.append(f"  FIX     : {counts.get('FIX', 0)}")
    lines.append(f"  REPLACE : {counts.get('REPLACE', 0)}")
    lines.append(f"  REVIEW  : {counts.get('REVIEW', 0)}")
    lines.append("")
    lines.append("-" * 70)
    lines.append(f"  {'ID':<20} {'Cell':<24} {'Q':>5} {'Category':<10} Reason")
    lines.append("-" * 70)

    for c in classified:
        tid = c["task_id"][:16]
        cell = c["cell_key"]
        q = c["quality_score"]
        cat = c["category"]
        reason = c["reason"]
        lines.append(f"  {tid:<20} {cell:<24} {q:>5.1f} {cat:<10} {reason}")

    lines.append("")
    lines.append("=" * 70)
    lines.append("  END OF REPORT")
    lines.append("=" * 70)

    report = "\n".join(lines)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  Saved {REPORT_PATH}")
    print(report)


if __name__ == "__main__":
    main()
