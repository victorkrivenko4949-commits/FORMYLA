#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 0: Reconciliation — Pre-generation count verification.

Purpose:
  Before any AI generation, reconcile all classification counts to guarantee
  data integrity. Extract KEEP/FIXED/REPLACE sets, verify invariants, compute
  per-cell replacement slots.

Output:
  l4_l5_finalization/reconciliation_report.json

Algorithm:
  1. Load stage4_classification.json -> 63 task_ids with category
  2. Load stage45_reclassification.json -> 40 reclassified task_ids with new_category
  3. Load stage5_fix_results.json -> 14 fix task_ids with outcome (fixed|replace)
  4. Compute 3 final disjoint sets:
     - KEEP_ids   = {Stage4.KEEP=3} ∪ {Stage45.new_category=KEEP=10} = 13
     - FIXED_ids  = {Stage5.outcome=fixed=4} = 4
     - REPLACE_ids = {Stage4.REPLACE=20} ∪ {Stage45.new_category=REPLACE=16}
                     ∪ {Stage5.outcome=replace=10} = 46
  5. Verify invariants:
     - |KEEP ∪ FIXED ∪ REPLACE| == 63
     - Pairwise intersections empty
     - No duplicates across files
  6. Load curated bank -> count valid existing tasks per cell
  7. Compute per-cell replacement slots:
     - needed_slots = max(0, 5 - valid_existing_count)
  8. Save reconciliation_report.json

Usage:
    python _05_stage0_reconciliation.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(WORK_DIR)
sys.path.insert(0, PROJECT_DIR)

STAGE4_PATH = os.path.join(WORK_DIR, "stage4_classification.json")
STAGE45_PATH = os.path.join(WORK_DIR, "stage45_reclassification.json")
STAGE5_PATH = os.path.join(WORK_DIR, "stage5_fix_results.json")
BANK_PATH = os.path.join(WORK_DIR, "..", "l4_l5_fill_output", "curated_bank_L4_L5_filled.json")
OUTPUT_PATH = os.path.join(WORK_DIR, "reconciliation_report.json")


def load_json(path: str, desc: str = "file") -> Any:
    """Load JSON file with error handling."""
    if not os.path.exists(path):
        print(f"ERROR: {desc} not found at {path}")
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"ERROR loading {desc}: {e}")
        sys.exit(1)


def extract_stage4_sets(stage4: Dict) -> tuple[Set[str], Set[str], Set[str], Set[str]]:
    """Extract KEEP, FIX, REPLACE sets from stage4_classification.json.
    Returns (all_ids, keep_ids, fix_ids, replace_ids)."""
    all_ids: Set[str] = set()
    keep: Set[str] = set()
    fix: Set[str] = set()
    replace: Set[str] = set()

    for item in stage4.get("classifications", []):
        task_id = item.get("task_id", "")
        category = item.get("category", "")
        if not task_id:
            continue
        all_ids.add(task_id)
        if category == "KEEP":
            keep.add(task_id)
        elif category == "FIX":
            fix.add(task_id)
        elif category == "REPLACE":
            replace.add(task_id)
        # REVIEW or other categories are ignored

    return all_ids, keep, fix, replace


def extract_stage45_reclass(stage45: Dict) -> tuple[Set[str], Set[str], Set[str]]:
    """Extract new_category sets from stage45_reclassification.json.
    Returns (keep_ids, fix_ids, replace_ids)."""
    keep: Set[str] = set()
    fix: Set[str] = set()
    replace: Set[str] = set()

    for item in stage45.get("reclassifications", []):
        task_id = item.get("task_id", "")
        new_cat = item.get("new_category", "")
        if not task_id:
            continue
        if new_cat == "KEEP":
            keep.add(task_id)
        elif new_cat == "FIX":
            fix.add(task_id)
        elif new_cat == "REPLACE":
            replace.add(task_id)

    return keep, fix, replace


def extract_stage5_outcomes(stage5: Dict) -> tuple[Set[str], Set[str]]:
    """Extract fixed and replace sets from stage5_fix_results.json.
    Returns (fixed_ids, replace_ids)."""
    fixed: Set[str] = set()
    replace: Set[str] = set()

    for item in stage5.get("results", []):
        task_id = item.get("task_id", "")
        outcome = item.get("outcome", "")
        if not task_id:
            continue
        if outcome == "fixed":
            fixed.add(task_id)
        elif outcome == "replace":
            replace.add(task_id)

    return fixed, replace


def collect_all_classification_ids(stage4: Dict, stage45: Dict, stage5: Dict) -> Dict[str, List[str]]:
    """Collect all task_ids from all 3 files, tracking duplicates.
    Returns {task_id: [file_list]}."""
    id_map: Dict[str, List[str]] = {}

    for item in stage4.get("classifications", []):
        tid = item.get("task_id", "")
        if tid:
            id_map.setdefault(tid, []).append("stage4")

    for item in stage45.get("reclassifications", []):
        tid = item.get("task_id", "")
        if tid:
            id_map.setdefault(tid, []).append("stage45")

    for item in stage5.get("results", []):
        tid = item.get("task_id", "")
        if tid:
            id_map.setdefault(tid, []).append("stage5")

    return id_map


def load_bank_cell_counts(bank_path: str) -> Dict[str, int]:
    """Load curated bank and count tasks per cell_key.
    Returns {cell_key: task_count}."""
    bank = load_json(bank_path, "curated bank")
    cell_counts: Dict[str, int] = {}
    for task in bank:
        ck = task.get("cell_key", "")
        if ck:
            cell_counts[ck] = cell_counts.get(ck, 0) + 1
    return cell_counts


def compute_per_cell_slots(
    replace_ids: Set[str],
    bank_path: str,
    stage4: Dict
) -> tuple[List[Dict], int]:
    """Compute per-cell replacement slots from REPLACE ids.

    For each unique cell_key among REPLACE ids:
      - count valid existing tasks in that cell (total tasks - REPLACE tasks in that cell)
      - needed_slots = max(0, 5 - valid_existing_count)
      - replacement_slots = min(len(replace_ids_in_cell), needed_slots)

    Returns (per_cell_slots, total_replacement_slots).
    """
    # Build mapping: cell_key -> list of replace task_ids
    cell_replace_map: Dict[str, List[str]] = {}
    # Also build a mapping: task_id -> cell_key from stage4
    task_id_to_cell: Dict[str, str] = {}
    for item in stage4.get("classifications", []):
        tid = item.get("task_id", "")
        ck = item.get("cell_key", "")
        if tid and ck:
            task_id_to_cell[tid] = ck

    # Also get cell_key from stage45 and stage5 for replace_ids that might not be in stage4
    # Actually all 63 ids should be in stage4. Let's verify and use stage4 as primary.

    for rid in replace_ids:
        ck = task_id_to_cell.get(rid, "")
        if ck:
            cell_replace_map.setdefault(ck, []).append(rid)

    # Count total tasks per cell from bank
    bank_cell_counts = load_bank_cell_counts(bank_path)

    # Also load the bank tasks themselves to count valid_existing
    # (total tasks in cell - replace tasks in cell that are actually in bank)
    bank = load_json(bank_path, "curated bank for slot calc")
    bank_tasks_by_cell: Dict[str, List[Dict]] = {}
    for task in bank:
        ck = task.get("cell_key", "")
        if ck:
            bank_tasks_by_cell.setdefault(ck, []).append(task)

    per_cell_slots: List[Dict] = []
    total_replacement_slots = 0

    for ck, rep_ids in sorted(cell_replace_map.items()):
        bank_tasks = bank_tasks_by_cell.get(ck, [])
        total_in_bank = len(bank_tasks)

        # Count how many of the replace_ids are actually in this cell in the bank
        # valid_existing = total_in_bank - replace_ids_in_bank
        replace_in_bank = [t for t in bank_tasks if t.get("import_key", "") in rep_ids or t.get("task_id", "") in rep_ids]
        replace_in_bank_count = len(replace_in_bank)

        valid_existing = total_in_bank - replace_in_bank_count
        needed_slots = max(0, 5 - valid_existing)
        replacement_slots = min(len(rep_ids), needed_slots)

        per_cell_slots.append({
            "cell_key": ck,
            "replace_ids_count": len(rep_ids),
            "replace_ids": rep_ids,
            "total_in_bank": total_in_bank,
            "replace_in_bank": replace_in_bank_count,
            "valid_existing": valid_existing,
            "needed_slots": needed_slots,
            "replacement_slots": replacement_slots
        })
        total_replacement_slots += replacement_slots

        print(f"  Cell {ck}: {len(rep_ids)} replace ids, "
              f"{total_in_bank} total in bank, "
              f"{replace_in_bank_count} replace in bank, "
              f"valid_existing={valid_existing}, "
              f"needed_slots={needed_slots}, "
              f"replacement_slots={replacement_slots}")

    return per_cell_slots, total_replacement_slots


def main():
    print("=" * 70)
    print("Stage 0: Reconciliation — Pre-generation Count Verification")
    print("=" * 70)

    # 1. Load all classification files
    print("\n[1/7] Loading classification files...")
    stage4 = load_json(STAGE4_PATH, "Stage 4 classification")
    stage45 = load_json(STAGE45_PATH, "Stage 4.5 reclassification")
    stage5 = load_json(STAGE5_PATH, "Stage 5 fix results")

    print(f"  Stage 4: {stage4.get('summary', {}).get('total', '?')} tasks")
    print(f"    KEEP={stage4.get('summary', {}).get('counts', {}).get('KEEP', 0)}, "
          f"FIX={stage4.get('summary', {}).get('counts', {}).get('FIX', 0)}, "
          f"REPLACE={stage4.get('summary', {}).get('counts', {}).get('REPLACE', 0)}")
    print(f"  Stage 4.5: {stage45.get('summary', {}).get('total_fix_analyzed', '?')} tasks")
    s45_counts = stage45.get('summary', {}).get('new_category_counts', {})
    print(f"    KEEP={s45_counts.get('KEEP', 0)}, "
          f"FIX={s45_counts.get('FIX', 0)}, "
          f"REPLACE={s45_counts.get('REPLACE', 0)}")
    print(f"  Stage 5: {stage5.get('summary', {}).get('total_fix_tasks', '?')} tasks")
    print(f"    FIXED={stage5.get('summary', {}).get('fixed', 0)}, "
          f"REPLACE={stage5.get('summary', {}).get('replace', 0)}")

    # 2. Extract sets
    print("\n[2/7] Extracting task_id sets...")
    s4_all, s4_keep, s4_fix, s4_replace = extract_stage4_sets(stage4)
    s45_keep, s45_fix, s45_replace = extract_stage45_reclass(stage45)
    s5_fixed, s5_replace = extract_stage5_outcomes(stage5)

    print(f"  Stage 4: all={len(s4_all)}, keep={len(s4_keep)}, fix={len(s4_fix)}, replace={len(s4_replace)}")
    print(f"  Stage 4.5: keep={len(s45_keep)}, fix={len(s45_fix)}, replace={len(s45_replace)}")
    print(f"  Stage 5: fixed={len(s5_fixed)}, replace={len(s5_replace)}")

    # 3. Compute final disjoint sets
    print("\n[3/7] Computing final disjoint sets...")
    keep_ids = s4_keep | s45_keep
    fixed_ids = s5_fixed
    replace_ids = s4_replace | s45_replace | s5_replace

    print(f"  KEEP_ids   = Stage4.KEEP({len(s4_keep)}) + Stage45.KEEP({len(s45_keep)}) = {len(keep_ids)}")
    print(f"  FIXED_ids  = Stage5.fixed({len(fixed_ids)}) = {len(fixed_ids)}")
    print(f"  REPLACE_ids = Stage4.REPLACE({len(s4_replace)}) + Stage45.REPLACE({len(s45_replace)}) + "
          f"Stage5.replace({len(s5_replace)}) = {len(replace_ids)}")

    # 4. Verify invariants
    print("\n[4/7] Verifying invariants...")
    union_all = keep_ids | fixed_ids | replace_ids
    total_unique = len(union_all)

    keep_fixed_intersection = keep_ids & fixed_ids
    keep_replace_intersection = keep_ids & replace_ids
    fixed_replace_intersection = fixed_ids & replace_ids

    expected_total = 63
    invariants = {
        "classified_unique_ids_equals_keep_plus_fixed_plus_replace": total_unique == expected_total,
        "keep_intersect_fixed_empty": len(keep_fixed_intersection) == 0,
        "keep_intersect_replace_empty": len(keep_replace_intersection) == 0,
        "fixed_intersect_replace_empty": len(fixed_replace_intersection) == 0,
    }

    print(f"  |KEEP ∪ FIXED ∪ REPLACE| = {total_unique} (expected {expected_total}) "
          f"{'[OK]' if total_unique == expected_total else ' FAIL'}")
    print(f"  KEEP ∩ FIXED = {keep_fixed_intersection} "
          f"{'[OK] empty' if len(keep_fixed_intersection) == 0 else ' NON-EMPTY'}")
    print(f"  KEEP ∩ REPLACE = {keep_replace_intersection} "
          f"{'[OK] empty' if len(keep_replace_intersection) == 0 else ' NON-EMPTY'}")
    print(f"  FIXED ∩ REPLACE = {fixed_replace_intersection} "
          f"{'[OK] empty' if len(fixed_replace_intersection) == 0 else ' NON-EMPTY'}")

    # 5. Check for duplicates across files
    print("\n[5/7] Checking for cross-file duplicates...")
    id_map = collect_all_classification_ids(stage4, stage45, stage5)
    duplicates = {tid: files for tid, files in id_map.items() if len(files) > 1}
    print(f"  Task IDs appearing in multiple files: {len(duplicates)}")
    for tid, files in sorted(duplicates.items()):
        print(f"    {tid}: {', '.join(files)}")

    # 6. Compute per-cell slots
    print("\n[6/7] Computing per-cell replacement slots...")
    print(f"  Loading bank from: {BANK_PATH}")
    per_cell_slots, total_replacement_slots = compute_per_cell_slots(
        replace_ids, BANK_PATH, stage4
    )

    print(f"\n  Total replacement slots across all affected cells: {total_replacement_slots}")
    print(f"  Affected cells: {len(per_cell_slots)}")

    # 7. Build and save report
    print("\n[7/7] Saving reconciliation report...")
    report = {
        "reconciliation_timestamp": datetime.now(timezone.utc).isoformat(),
        "stage3_unique_task_ids": expected_total,
        "stage4_classified_task_ids": len(s4_all),
        "stage45_reclassified_task_ids": len(s45_keep) + len(s45_fix) + len(s45_replace),
        "stage5_fix_task_ids": len(s5_fixed) + len(s5_replace),
        "final_sets": {
            "keep": {
                "count": len(keep_ids),
                "task_ids": sorted(list(keep_ids))
            },
            "fixed": {
                "count": len(fixed_ids),
                "task_ids": sorted(list(fixed_ids))
            },
            "replace": {
                "count": len(replace_ids),
                "task_ids": sorted(list(replace_ids))
            }
        },
        "total_unique": total_unique,
        "expected_total": expected_total,
        "invariants": invariants,
        "cross_file_duplicates": {
            tid: files for tid, files in duplicates.items()
        },
        "per_cell_slots": per_cell_slots,
        "total_replacement_slots": total_replacement_slots,
        "total_fixed_tasks": len(fixed_ids),
        "verdict": "PASS" if all(invariants.values()) and total_unique == expected_total else "FAIL"
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n  Report saved to: {OUTPUT_PATH}")
    print(f"  Verdict: {report['verdict']}")

    # Summary
    print("\n" + "=" * 70)
    print("RECONCILIATION SUMMARY")
    print("=" * 70)
    print(f"  KEEP   = {len(keep_ids)}")
    print(f"  FIXED  = {len(fixed_ids)}")
    print(f"  REPLACE = {len(replace_ids)}")
    print(f"  TOTAL  = {total_unique}")
    print(f"  13 + 4 + 46 = {13 + 4 + 46}")
    print(f"  Expected: {expected_total}")
    print(f"  Match: {'[OK]' if total_unique == expected_total else ' MISMATCH!'}")
    print(f"  Total replacement slots to generate: {total_replacement_slots}")
    print(f"  Verdict: {report['verdict']}")

    if report['verdict'] == 'FAIL':
        print("\n  WARNING: Reconciliation FAILED. Do NOT proceed to Stage 6.")
        print("  Fix classification data before continuing.")
        sys.exit(1)
    else:
        print("\n  [OK] Reconciliation PASSED. Proceed to Stage 6.")


if __name__ == "__main__":
    main()
