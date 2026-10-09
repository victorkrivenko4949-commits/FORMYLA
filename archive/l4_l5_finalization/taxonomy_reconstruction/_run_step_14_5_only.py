#!/usr/bin/env python3
"""
Re-run step_14_5 in isolation to rebuild the bank_taxonomy_crosswalk.jsonl
with the updated curated topic mapping (phantom T042/T043 fix + Category A fixes).

Usage:
    cd l4_l5_finalization/taxonomy_reconstruction
    python _run_step_14_5_only.py
"""

import sys
import os

# Add the taxonomy_reconstruction dir to path so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import from _taxonomy_reconstruct
from _taxonomy_reconstruct import (
    step_14_3, step_14_4, step_14_5,
    step_14_6, step_14_7,
    build_curated_topic_mapping,
    OUT_DIR
)

def main():
    print("=" * 60)
    print("Re-running step_14_5 with updated topic mapping")
    print("=" * 60)

    # Step 14.3 — rebuild canonical_dict from taxonomy_by_grade.json
    # (deterministic, no side effects except writing output files)
    print("\n--- Step 14.3 (canonical taxonomy) ---")
    canonical, canonical_dict = step_14_3()

    # Step 14.4 — rebuild task_lineage from checkpoint sources
    # (deterministic, no side effects except writing output files)
    print("\n--- Step 14.4 (task lineage) ---")
    task_lineage = step_14_4()

    # Step 14.5 — rebuild crosswalk with UPDATED mapping
    print("\n--- Step 14.5 (crosswalk) ---")
    crosswalk, crosswalk_summary = step_14_5(task_lineage, canonical_dict)

    # Print summary
    print("\n" + "=" * 60)
    print("CROSSWALK REBUILD COMPLETE")
    print("=" * 60)
    print(f"  Total crosswalk entries: {len(crosswalk)}")
    print(f"  Mapped (validated): {crosswalk_summary.get('mapped_with_validated_cell_key', 0)}")
    print(f"  Mapped (total): {crosswalk_summary.get('mapped_total', 0)}")
    print(f"  Unresolved: {crosswalk_summary.get('unresolved', 0)}")
    print(f"  By method: {crosswalk_summary.get('mapped_by_method', {})}")
    print(f"  Coverage: {crosswalk_summary.get('coverage', 'N/A')}")
    print()

    # Also run step_14_6 and step_14_7 since they depend on crosswalk
    print("\n--- Step 14.6 (conflicts) ---")
    conflicts, grade_conflicts = step_14_6(crosswalk)

    print("\n--- Step 14.7 (bank_by_cell) ---")
    bank_by_cell, bank_report = step_14_7(crosswalk, canonical_dict)

    print("\n" + "=" * 60)
    print("POST-14.5 STEPS COMPLETE (14.6 + 14.7)")
    print("=" * 60)
    print(f"  Mapping conflicts: {len(conflicts)}")
    print(f"  Grade mismatches: {len(grade_conflicts)}")
    print(f"  Cells with tasks: {len(bank_by_cell)}")
    print(f"  All outputs in: {OUT_DIR}")
    print()

if __name__ == "__main__":
    main()
