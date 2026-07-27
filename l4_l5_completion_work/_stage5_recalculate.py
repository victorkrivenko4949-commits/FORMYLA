#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STAGE 5: Recalculate generation_needed after Stages 2-4 audits.
===============================================================

Purpose:
  After running re-audits for uncertain tasks (Stage 2), overflow tasks (Stage 3),
  and rejected duplicates (Stage 4), recompute the actual per-cell gaps and
  generate a generation_plan.csv for targeted generation (Stage 6).

Inputs:
  - l4_l5_fill_output/fill_audit.json       -> current cell state
  - l4_l5_completion_work/stage4_reinstated_candidates.json -> possible reinstatements

Outputs:
  - l4_l5_completion_work/generation_plan.csv  -> cells needing tasks, sorted by priority
  - l4_l5_completion_work/stage5_report.txt     -> summary report
"""

import json
import csv
import os

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
FILL_OUTPUT_DIR = os.path.join(os.path.dirname(WORK_DIR), "l4_l5_fill_output")

AUDIT_PATH = os.path.join(FILL_OUTPUT_DIR, "fill_audit.json")
REINSTATED_PATH = os.path.join(WORK_DIR, "stage4_reinstated_candidates.json")
OUTPUT_PLAN = os.path.join(WORK_DIR, "generation_plan.csv")
OUTPUT_REPORT = os.path.join(WORK_DIR, "stage5_report.txt")


def main():
    print("=" * 70)
    print("  STAGE 5: RECALCULATE GENERATION NEEDED")
    print("=" * 70)

    # 1. Load current cell state from fill_audit.json
    print(f"\n[1] Loading cell state from: {AUDIT_PATH}")
    with open(AUDIT_PATH, "r", encoding="utf-8") as f:
        audit = json.load(f)

    summary = audit["summary"]
    print(f"    Total cells: {summary['total_cells']}")
    print(f"    Full cells: {summary['full_cells']}")
    print(f"    Total tasks added: {summary['total_tasks_added']}")

    # Build dict: cell_key -> {task_count, slots_remaining, theme_name, grade, level, theme_id, subtopic_idx, subtopic}
    cell_state = {}
    for cs in audit["cell_stats"]:
        cell_state[cs["cell_key"]] = {
            "task_count": cs["task_count"],
            "slots_remaining": cs["slots_remaining"],
            "is_full": cs["is_full"],
            "grade": cs["grade"],
            "level": cs["level"],
            "theme_id": cs["theme_id"],
            "theme_name": cs["theme_name"],
            "subtopic_idx": cs["subtopic_idx"],
            "subtopic": cs["subtopic"],
        }

    # Current counts
    incomplete_cells = [ck for ck, cs in cell_state.items() if not cs["is_full"]]
    total_slots_remaining = sum(cell_state[ck]["slots_remaining"] for ck in incomplete_cells)
    empty_cells = [ck for ck, cs in cell_state.items() if cs["task_count"] == 0]
    partial_cells = [ck for ck, cs in cell_state.items() if 0 < cs["task_count"] < 5]

    print(f"\n    BEFORE reinstatement consideration:")
    print(f"    Incomplete cells: {len(incomplete_cells)}")
    print(f"    Empty cells (0 tasks): {len(empty_cells)}")
    print(f"    Partial cells (1-4 tasks): {len(partial_cells)}")
    print(f"    Total slots remaining: {total_slots_remaining}")

    # 2. Load Stage 4 reinstated candidates
    print(f"\n[2] Loading reinstated candidates from: {REINSTATED_PATH}")
    reinstated = []
    if os.path.exists(REINSTATED_PATH):
        with open(REINSTATED_PATH, "r", encoding="utf-8") as f:
            reinstated = json.load(f)
    print(f"    Total reinstatement candidates: {len(reinstated)}")

    # Map reinstated tasks to cells and see which match gaps
    reinstatement_by_cell = {}
    for item in reinstated:
        info = item.get("verdict_info", {})
        cell_key = info.get("target_cell", "")
        if cell_key:
            if cell_key not in reinstatement_by_cell:
                reinstatement_by_cell[cell_key] = []
            reinstatement_by_cell[cell_key].append({
                "confidence": info.get("confidence", 0),
                "statement": item.get("task", {}).get("statement", "")[:80],
                "reason": item.get("task", {}).get("reason", ""),
            })

    # Find reinstatements that match gap cells
    gap_matches = []
    for cell_key, tasks in reinstatement_by_cell.items():
        if cell_key in cell_state and not cell_state[cell_key]["is_full"]:
            gap_matches.append({
                "cell_key": cell_key,
                "slots_remaining": cell_state[cell_key]["slots_remaining"],
                "reinstatements": len(tasks),
                "tasks": tasks[:3],  # first 3 as sample
            })

    print(f"    Unique cells with reinstatements: {len(reinstatement_by_cell)}")
    print(f"    Reinstatements matching gap cells: {len(gap_matches)}")

    # 3. Compute adjusted gaps considering reinstatements
    print(f"\n[3] Computing generation plan...")

    plan_rows = []
    for ck, cs in sorted(cell_state.items()):
        needed = cs["slots_remaining"]

        # Check if reinstated candidates can fill some of this gap
        reinstatements_available = len(reinstatement_by_cell.get(ck, []))
        reinstatements_usable = min(reinstatements_available, needed)
        adjusted_needed = needed - reinstatements_usable

        plan_rows.append({
            "cell_key": ck,
            "grade": cs["grade"],
            "level": cs["level"],
            "theme_id": cs["theme_id"],
            "theme_name": cs["theme_name"],
            "subtopic_idx": cs["subtopic_idx"],
            "subtopic": cs["subtopic"],
            "current_count": cs["task_count"],
            "needed": needed,
            "reinstatements_available": reinstatements_available,
            "reinstatements_usable": reinstatements_usable,
            "adjusted_needed": adjusted_needed,
        })

    # Sort: highest adjusted_needed first, then lowest current_count
    plan_rows.sort(key=lambda r: (-r["adjusted_needed"], r["current_count"], r["cell_key"]))

    # 4. Write generation_plan.csv
    print(f"\n[4] Writing generation plan to: {OUTPUT_PLAN}")
    fieldnames = [
        "cell_key", "grade", "level", "theme_id", "theme_name",
        "subtopic_idx", "subtopic", "current_count", "needed",
        "reinstatements_available", "reinstatements_usable", "adjusted_needed",
    ]
    with open(OUTPUT_PLAN, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(plan_rows)
    print(f"    Written {len(plan_rows)} rows")

    # 5. Write report
    print(f"\n[5] Writing report to: {OUTPUT_REPORT}")
    total_needed = sum(r["needed"] for r in plan_rows)
    total_adjusted = sum(r["adjusted_needed"] for r in plan_rows)
    total_reinstated_usable = sum(r["reinstatements_usable"] for r in plan_rows)

    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("  STAGE 5: GENERATION PLAN REPORT\n")
        f.write("=" * 70 + "\n\n")

        f.write("CURRENT STATE (from fill_audit.json):\n")
        f.write(f"  Total cells: {summary['total_cells']}\n")
        f.write(f"  Full cells: {summary['full_cells']}\n")
        f.write(f"  Total tasks added: {summary['total_tasks_added']}\n")
        f.write(f"  Classified: {summary['classified_count']}\n")
        f.write(f"  Duplicates removed: {summary['duplicates_removed']}\n")
        f.write(f"  Uncertain: {summary['uncertain']}\n")
        f.write(f"  Overflow: {summary['overflow']}\n\n")

        f.write("GAP ANALYSIS:\n")
        f.write(f"  Incomplete cells: {len(incomplete_cells)}\n")
        f.write(f"  Empty cells (0/5): {len(empty_cells)}\n")
        f.write(f"  Partial cells (1-4/5): {len(partial_cells)}\n")
        f.write(f"  Total slots remaining: {total_slots_remaining}\n\n")

        f.write("STAGE 4 REINSTATEMENTS:\n")
        f.write(f"  Total reinstatement candidates: {len(reinstated)}\n")
        f.write(f"  Unique cells with candidates: {len(reinstatement_by_cell)}\n")
        f.write(f"  Candidates matching active gaps: {len(gap_matches)}\n")
        f.write(f"  Usable reinstatements: {total_reinstated_usable}\n\n")

        f.write("GENERATION PLAN:\n")
        f.write(f"  Total needed (before reinstatements): {total_needed}\n")
        f.write(f"  Total needed (after reinstatements):  {total_adjusted}\n")
        f.write(f"  Cells needing generation: {sum(1 for r in plan_rows if r['adjusted_needed'] > 0)}\n\n")

        if gap_matches:
            f.write("GAP-MATCHING REINSTATEMENTS:\n")
            for gm in gap_matches:
                f.write(f"  [{gm['cell_key']}] slots_remaining={gm['slots_remaining']}, "
                       f"reinstatements={gm['reinstatements']}\n")
                for t in gm["tasks"][:2]:
                    f.write(f"    - conf={t['confidence']}, reason={t['reason']}\n")
            f.write("\n")

        f.write("TOP 30 CELLS NEEDING GENERATION:\n")
        f.write(f"{'Cell Key':<25} {'Grade':<6} {'Lvl':<4} {'Curr':<6} {'Need':<6} {'Adj':<6} {'Theme':<50}\n")
        f.write("-" * 100 + "\n")
        for r in plan_rows[:30]:
            if r["adjusted_needed"] > 0:
                f.write(f"{r['cell_key']:<25} {r['grade']:<6} {r['level']:<4} "
                       f"{r['current_count']:<6} {r['needed']:<6} {r['adjusted_needed']:<6} "
                       f"{r['theme_name'][:48]:<50}\n")
        f.write("\n")

        f.write("ALL INCOMPLETE CELLS:\n")
        f.write(f"{'Cell Key':<25} {'Grade':<6} {'Lvl':<4} {'Curr':<6} {'Need':<6} {'Adj':<6} {'Theme':<50}\n")
        f.write("-" * 100 + "\n")
        for r in plan_rows:
            if r["adjusted_needed"] > 0:
                f.write(f"{r['cell_key']:<25} {r['grade']:<6} {r['level']:<4} "
                       f"{r['current_count']:<6} {r['needed']:<6} {r['adjusted_needed']:<6} "
                       f"{r['theme_name'][:48]:<50}\n")
        f.write("\n")

        f.write("=" * 70 + "\n")
        f.write("  END OF STAGE 5 REPORT\n")
        f.write("=" * 70 + "\n")

    print(f"\n    Total needed (before reinstatements): {total_needed}")
    print(f"    Total needed (after reinstatements):  {total_adjusted}")
    print(f"    Cells needing generation: {sum(1 for r in plan_rows if r['adjusted_needed'] > 0)}")
    print(f"\n{'='*70}")
    print(f"  STAGE 5 COMPLETE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
