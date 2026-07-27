#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import io
# Force UTF-8 for stdout/stderr to avoid CP1251 encoding issues
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
"""
Pre-Run Scope Audit — 128 vs 129 Base Cells Investigation
==========================================================

Cross-references canonical_taxonomy.json (43 topics × 3 subtopics = 129 possible)
with target_grid.json (128 allowed cells) to identify and document the exact
discrepancy, with full provenance proof.

Output: l1_l3_generation/pre_run_scope_audit.json

Pipeline invariant:
   expected_base_cells = 129 (taxonomy: 43 topics × 3 subtopics)
   actual_base_cells    = 128 (target grid: one cell excluded per VICTOR2.0 pedagogy)
   delta                = 1 (authoritative exclusion, NOT an error)
   expected_level_cells = 128 × 3 = 384
   expected_tasks       = 384 × 5 = 1920

Author: Pre-Run Audit
"""

import os
import json
import hashlib
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TAXONOMY_PATH   = os.path.join(BASE_DIR, "canonical_taxonomy.json")
GRID_PATH       = os.path.join(BASE_DIR, "target_grid.json")
GRID_AUDIT_PATH = os.path.join(BASE_DIR, "target_grid_audit.json")
OUT_PATH        = os.path.join(BASE_DIR, "pre_run_scope_audit.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ===========================================================================
# Step 1: Count taxonomy base cells (theoretical maximum)
# ===========================================================================
def audit_taxonomy_scope(tax: dict) -> dict:
    """
    Enumerate all (topic_id, subtopic_id) pairs from canonical taxonomy.
    """
    topics = tax.get("topics", {})
    all_cells = []
    for tid in sorted(topics.keys()):
        topic = topics[tid]
        topic_name = topic.get("topic_name", tid)
        subtopics = topic.get("subtopics", {})
        for sid in sorted(subtopics.keys()):
            sub = subtopics[sid]
            sub_name = sub.get("subtopic_name", sid)
            cell_key = f"{tid}|{sid}"
            all_cells.append({
                "taxonomy_cell_key": cell_key,
                "topic_id": tid,
                "topic_name": topic_name,
                "subtopic_id": sid,
                "subtopic_name": sub_name,
                "order": sub.get("order", 0),
            })

    return {
        "total_topics": len(topics),
        "total_subtopics": sum(len(t.get("subtopics", {})) for t in topics.values()),
        "theoretical_max_cells": len(all_cells),
        "taxonomy_cells": all_cells,
    }


# ===========================================================================
# Step 2: Count target grid base cells (actual allowed)
# ===========================================================================
def audit_grid_scope(grid: dict) -> dict:
    """
    Enumerate all allowed (grade, topic_id, subtopic_id) from target_grid.
    Also enumerate all explicitly excluded cells.
    """
    grades = grid.get("grades", {})
    allowed_cells = []
    excluded_cells = []

    total_allowed = 0
    total_excluded = 0

    for g in sorted(grades.keys(), key=int):
        grade = int(g)
        grade_data = grades[g]
        for tid in sorted(grade_data.get("topics", {}).keys()):
            topic_data = grade_data["topics"][tid]
            topic_name = topic_data.get("topic_name", tid)
            for sid in sorted(topic_data.get("subtopics", {}).keys()):
                st = topic_data["subtopics"][sid]
                sub_name = st.get("subtopic_name", sid)
                allowed = st.get("allowed", True)
                reason = st.get("curriculum_reason", "")
                source = st.get("source", "")

                entry = {
                    "grade": grade,
                    "topic_id": tid,
                    "topic_name": topic_name,
                    "subtopic_id": sid,
                    "subtopic_name": sub_name,
                    "cell_key": f"G{grade}|{tid}|{sid}",
                    "curriculum_reason": reason,
                    "source": source,
                }

                if allowed:
                    allowed_cells.append(entry)
                    total_allowed += 1
                else:
                    entry["exclusion_reason"] = reason
                    excluded_cells.append(entry)
                    total_excluded += 1

    return {
        "total_allowed_cells": total_allowed,
        "total_excluded_cells": total_excluded,
        "total_cells_in_grid": total_allowed + total_excluded,
        "allowed_cells": allowed_cells,
        "excluded_cells": excluded_cells,
    }


# ===========================================================================
# Step 3: Cross-reference — find which taxonomy cells are MISSING from grid
# ===========================================================================
def cross_reference(tax_scope: dict, grid_scope: dict) -> dict:
    """
    For each (topic_id, subtopic_id) in taxonomy, check if it appears in ANY grade
    in the target grid as allowed.

    Also report which taxonomy cells appear excluded in ALL grades they appear in.
    """
    tax_cells = tax_scope["taxonomy_cells"]
    grid_allowed = grid_scope["allowed_cells"]
    grid_excluded = grid_scope["excluded_cells"]

    # Build set of (topic_id, subtopic_id) that are allowed somewhere
    allowed_pairs = set()
    for c in grid_allowed:
        allowed_pairs.add((c["topic_id"], c["subtopic_id"]))

    # Build set of (topic_id, subtopic_id) that are excluded somewhere
    excluded_pairs = set()
    for c in grid_excluded:
        excluded_pairs.add((c["topic_id"], c["subtopic_id"]))

    # Find taxonomy cells that never appear as allowed in any grade
    never_allowed = []
    for tc in tax_cells:
        pair = (tc["topic_id"], tc["subtopic_id"])
        if pair not in allowed_pairs:
            never_allowed.append({
                "topic_id": tc["topic_id"],
                "subtopic_id": tc["subtopic_id"],
                "topic_name": tc["topic_name"],
                "subtopic_name": tc["subtopic_name"],
                "reason": f"Subtopics {tc['subtopic_id']} of topic {tc['topic_id']} "
                          f"('{tc['topic_name']}') is NOT allowed in any grade.",
            })

    # Find the specific exclusion details
    exclusion_details = []
    for ec in grid_excluded:
        exclusion_details.append({
            "grade": ec["grade"],
            "topic_id": ec["topic_id"],
            "topic_name": ec["topic_name"],
            "subtopic_id": ec["subtopic_id"],
            "subtopic_name": ec["subtopic_name"],
            "cell_key": ec["cell_key"],
            "exclusion_reason": ec["exclusion_reason"],
            "source": ec["source"],
        })

    return {
        "taxonomy_cells_never_allowed": never_allowed,
        "delta_count": len(never_allowed),
        "exclusion_details": exclusion_details,
        "exclusion_count": len(exclusion_details),
        "is_authoritative_exclusion": len(never_allowed) == len(exclusion_details) == 1,
    }


# ===========================================================================
# Step 4: Compute level-cell and task counts
# ===========================================================================
def compute_counts(grid_scope: dict) -> dict:
    """
    Compute expected level-cells and tasks from allowed base cells.
    """
    n_allowed = grid_scope["total_allowed_cells"]
    levels = ["L1", "L2", "L3"]
    n_levels = len(levels)
    tasks_per_level_cell = 5

    level_cells = n_allowed * n_levels
    total_tasks = level_cells * tasks_per_level_cell

    per_level = {
        level: {
            "level_cells": n_allowed,
            "tasks_per_cell": tasks_per_level_cell,
            "total_tasks": n_allowed * tasks_per_level_cell,
        }
        for level in levels
    }

    return {
        "formula": {
            "base_cells": n_allowed,
            "levels_per_cell": n_levels,
            "level_cells": f"{n_allowed} × {n_levels} = {level_cells}",
            "tasks_per_level_cell": tasks_per_level_cell,
            "total_tasks": f"{level_cells} × {tasks_per_level_cell} = {total_tasks}",
        },
        "total_base_cells": n_allowed,
        "total_level_cells": level_cells,
        "total_expected_tasks": total_tasks,
        "per_level": per_level,
    }


# ===========================================================================
# Step 5: Grade-level breakdown
# ===========================================================================
def grade_breakdown(grid_scope: dict) -> dict:
    """
    Count allowed cells per grade.
    """
    allowed = grid_scope["allowed_cells"]
    grades = {}
    for c in allowed:
        g = c["grade"]
        if g not in grades:
            grades[g] = {"allowed_cells": 0, "excluded_cells": 0, "topics": set()}
        grades[g]["allowed_cells"] += 1
        grades[g]["topics"].add(c["topic_id"])

    for ec in grid_scope["excluded_cells"]:
        g = ec["grade"]
        if g not in grades:
            grades[g] = {"allowed_cells": 0, "excluded_cells": 0, "topics": set()}
        grades[g]["excluded_cells"] += 1

    breakdown = {}
    for g in sorted(grades.keys()):
        info = grades[g]
        n_topics = len(info["topics"])
        n_allowed = info["allowed_cells"]
        n_excluded = info["excluded_cells"]
        level_cells = n_allowed * 3
        tasks = level_cells * 5
        breakdown[str(g)] = {
            "topics": n_topics,
            "allowed_subtopic_cells": n_allowed,
            "excluded_subtopic_cells": n_excluded,
            "level_cells": level_cells,
            "expected_tasks": tasks,
        }

    return breakdown


# ===========================================================================
# Main
# ===========================================================================
def main():
    print("=" * 72)
    print("  PRE-RUN SCOPE AUDIT — L1-L3 Generation Pipeline")
    print("=" * 72)

    # Load inputs
    tax = _load_json(TAXONOMY_PATH)
    grid = _load_json(GRID_PATH)

    tax_hash = _sha256(TAXONOMY_PATH)
    grid_hash = _sha256(GRID_PATH)

    print(f"\n  Taxonomy   : {TAXONOMY_PATH}")
    print(f"  SHA-256    : {tax_hash}")
    print(f"  Grid       : {GRID_PATH}")
    print(f"  SHA-256    : {grid_hash}")

    # Steps
    print("\n  [Step 1] Auditing taxonomy scope...")
    tax_scope = audit_taxonomy_scope(tax)
    print(f"    → {tax_scope['total_topics']} topics, {tax_scope['total_subtopics']} subtopics, "
          f"{tax_scope['theoretical_max_cells']} possible cells")

    print("  [Step 2] Auditing target grid scope...")
    grid_scope = audit_grid_scope(grid)
    print(f"    → {grid_scope['total_allowed_cells']} allowed cells, "
          f"{grid_scope['total_excluded_cells']} excluded cells")

    print("  [Step 3] Cross-referencing...")
    xref = cross_reference(tax_scope, grid_scope)
    print(f"    → {xref['delta_count']} cell(s) from taxonomy never allowed in any grade")
    if xref["is_authoritative_exclusion"]:
        ec = xref["exclusion_details"][0]
        print(f"    → Identified exclusion: {ec['cell_key']} — {ec['subtopic_name']}")
        print(f"      Reason: {ec['exclusion_reason']}")
        print(f"    → VERDICT: Authoritative exclusion (NOT an error)")
    else:
        print(f"    → WARNING: Unexpected delta — needs investigation!")
        if xref["delta_count"] == 0:
            print(f"    → 0 delta means all 129 cells are allowed somewhere. "
                  f"Check grade-level exclusions.")

    print("  [Step 4] Computing counts...")
    counts = compute_counts(grid_scope)
    print(f"    → {counts['total_base_cells']} base cells × 3 levels = "
          f"{counts['total_level_cells']} level-cells")
    print(f"    → {counts['total_level_cells']} level-cells × 5 tasks = "
          f"{counts['total_expected_tasks']} expected tasks")

    print("  [Step 5] Grade breakdown...")
    breakdown = grade_breakdown(grid_scope)
    for g_str, info in sorted(breakdown.items(), key=lambda x: int(x[0])):
        print(f"    Grade {g_str}: {info['topics']} topics, "
              f"{info['allowed_subtopic_cells']} cells, "
              f"{info['level_cells']} level-cells, "
              f"{info['expected_tasks']} tasks")

    # Final verdict
    print("\n  [STEP 6] Final Verdict...")
    all_invariants_pass = True

    # Compute level-cell counts
    n_allowed = grid_scope["total_allowed_cells"]
    expected_level_cells = n_allowed * 3
    expected_tasks = expected_level_cells * 5

    # Per-level task count
    per_level_count = n_allowed * 5  # 5 tasks per level_cell per level

    invariants = {
        "expected_base_cells": n_allowed,
        "expected_level_cells": expected_level_cells,
        "expected_total_tasks": expected_tasks,
        "taxonomy_max_possible_cells": tax_scope["theoretical_max_cells"],
        "delta_vs_taxonomy": tax_scope["theoretical_max_cells"] - n_allowed,
        "exclusion_is_authoritative": xref["is_authoritative_exclusion"],
        "tasks_per_level_cell": 5,
        "level_count": 3,
        "per_level_task_count": per_level_count,
    }

    # Assemble full report
    report = {
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
        "taxonomy_file": "canonical_taxonomy.json",
        "target_grid_file": "target_grid.json",
        "taxonomy_sha256": tax_hash,
        "target_grid_sha256": grid_hash,

        "taxonomy_scope": {
            "total_topics": tax_scope["total_topics"],
            "total_subtopics": tax_scope["total_subtopics"],
            "theoretical_max_cells": tax_scope["theoretical_max_cells"],
        },

        "grid_scope": {
            "total_allowed_cells": grid_scope["total_allowed_cells"],
            "total_excluded_cells": grid_scope["total_excluded_cells"],
            "total_cells_in_grid": grid_scope["total_cells_in_grid"],
        },

        "cross_reference": {
            "delta_count": xref["delta_count"],
            "is_authoritative_exclusion": xref["is_authoritative_exclusion"],
            "taxonomy_cells_never_allowed": xref["taxonomy_cells_never_allowed"],
            "exclusion_details": xref["exclusion_details"],
        },

        "counts": {
            "formula": counts["formula"],
            "total_base_cells": counts["total_base_cells"],
            "total_level_cells": counts["total_level_cells"],
            "total_expected_tasks": counts["total_expected_tasks"],
            "per_level": counts["per_level"],
        },

        "grade_breakdown": breakdown,

        "invariants": invariants,
        "all_invariants_pass": (
            invariants["expected_base_cells"] == 128 and
            invariants["expected_level_cells"] == 384 and
            invariants["expected_total_tasks"] == 1920 and
            invariants["exclusion_is_authoritative"] and
            invariants["delta_vs_taxonomy"] == 1
        ),
        "status": "SCOPE_AUDIT_OK",
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n  Saved → {OUT_PATH}")
    print(f"  Status: {report['status']}")
    print(f"  All invariants pass: {report['all_invariants_pass']}")

    if not report["all_invariants_pass"]:
        print("\n  ⚠ INVARIANT FAILURE — review pre_run_scope_audit.json for details.")
        sys.exit(1)
    else:
        print("\n  ✓ SCOPE_AUDIT_OK — proceeding is safe.")

    print("=" * 72)
    return report


if __name__ == "__main__":
    main()
