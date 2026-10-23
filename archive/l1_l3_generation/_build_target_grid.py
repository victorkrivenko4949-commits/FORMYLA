#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Builds target_grid.json and target_grid_audit.json from canonical_taxonomy.json
using the VICTOR2.0 approved grade distribution.

Pipeline step: taxonomy -> grade mapping -> target grid -> generation

Output:
  - l1_l3_generation/target_grid.json
  - l1_l3_generation/target_grid_audit.json
"""

import json
import hashlib
import sys
import os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TAXONOMY_PATH = os.path.join(BASE_DIR, "canonical_taxonomy.json")
GRID_PATH = os.path.join(BASE_DIR, "target_grid.json")
AUDIT_PATH = os.path.join(BASE_DIR, "target_grid_audit.json")

# ============================================================================
# VICTOR2.0 APPROVED GRADE DISTRIBUTION
# Each grade maps to the topic IDs that are approved for that grade.
# Source: VICTOR2.0 generation plan (one topic per class principle).
# ============================================================================
VICTOR2_GRADE_MAP = {
    5:  ["T002", "T022", "T008", "T004", "T024", "T005"],
    6:  ["T006", "T007", "T032", "T033", "T016", "T018"],
    7:  ["T026", "T025", "T023", "T027", "T019", "T003"],
    8:  ["T042", "T011", "T012", "T037", "T009", "T017"],
    9:  ["T038", "T020", "T010", "T015", "T036", "T035"],
    10: ["T039", "T013", "T014", "T028", "T029", "T030"],
    11: ["T021", "T040", "T034", "T043", "T031", "T041", "T001"],
}

# ============================================================================
# SUBTOPIC EXCLUSIONS
# If a subtopic does NOT correspond to the school program and age for that
# grade, it is excluded entirely (not simplified, not included).
# Key: "G{grade}|T{topic_id}|S{subtopic_id}"
# ============================================================================
SUBS_EXCLUDED = {
    # Grade 8: T042 (Числа, индукция, алгоритмы)
    #   S1 (Комплексные числа) — complex numbers are not in the 8th-grade
    #   standard curriculum (typically 10-11 grade in Russian schools).
    "G8|T042|S1": "Комплексные числа не входят в программу 8 класса (изучаются в 10-11 классе).",
}

LEVELS = ["L1", "L2", "L3"]
TASKS_PER_SLOT = 5


def load_taxonomy(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["topics"]


def compute_sha256(data: dict) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_grid(taxonomy: dict) -> dict:
    """
    Build target_grid.json with the following structure:
    {
      "schema_version": "1.0",
      "grade_mapping_source": "VICTOR2.0_approved_distribution",
      "levels": {"L1": "ordinary_school", "L2": "school_stage_vseros", "L3": "municipal_stage_vseros"},
      "tasks_per_slot": 5,
      "grades": {
        "5": {
          "topics": {
            "T002": {
              "topic_name": "...",
              "subtopics": {
                "S0": {"subtopic_name": "...", "allowed": true, "curriculum_reason": "..."},
                "S1": {"subtopic_name": "...", "allowed": true, "curriculum_reason": "..."},
                "S2": {"subtopic_name": "...", "allowed": true, "curriculum_reason": "..."}
              }
            },
            ...
          }
        },
        ...
      }
    }
    """
    grades = {}
    for grade in sorted(VICTOR2_GRADE_MAP.keys()):
        grade_key = str(grade)
        topic_ids = VICTOR2_GRADE_MAP[grade]
        topics_dict = {}
        for tid in topic_ids:
            if tid not in taxonomy:
                print(f"[WARN] Topic {tid} not found in taxonomy, skipping for grade {grade}")
                continue
            topic_data = taxonomy[tid]
            topic_name = topic_data["topic_name"]
            subtopics_data = topic_data["subtopics"]
            subs_dict = {}
            for sid in ["S0", "S1", "S2"]:
                if sid not in subtopics_data:
                    print(f"[WARN] Subtopic {sid} not found in topic {tid}, skipping")
                    continue
                sub_name = subtopics_data[sid]["subtopic_name"]
                cell_key = f"G{grade}|{tid}|{sid}"
                if cell_key in SUBS_EXCLUDED:
                    subs_dict[sid] = {
                        "subtopic_name": sub_name,
                        "allowed": False,
                        "curriculum_reason": SUBS_EXCLUDED[cell_key],
                        "source": "pedagogical_review"
                    }
                else:
                    reason = _default_reason(grade, tid, sid, topic_name, sub_name)
                    subs_dict[sid] = {
                        "subtopic_name": sub_name,
                        "allowed": True,
                        "curriculum_reason": reason,
                        "source": "curriculum_alignment"
                    }
            topics_dict[tid] = {
                "topic_name": topic_name,
                "subtopics": subs_dict
            }
        grades[grade_key] = {
            "topics": topics_dict
        }

    grid = {
        "schema_version": "1.0",
        "grade_mapping_source": "VICTOR2.0_approved_distribution",
        "levels": {
            "L1": "ordinary_school",
            "L2": "school_stage_vseros",
            "L3": "municipal_stage_vseros"
        },
        "tasks_per_slot": TASKS_PER_SLOT,
        "grades": grades
    }
    return grid


def _default_reason(grade: int, tid: str, sid: str, topic_name: str, sub_name: str) -> str:
    """Generate a pedagogical curriculum reason for including this subtopic."""
    if sid == "S0":
        order_desc = "первая подтема"
    elif sid == "S1":
        order_desc = "вторая подтема"
    else:
        order_desc = "третья подтема"

    return (
        f"Тема «{topic_name}» ({tid}) включена в программу {grade} класса согласно "
        f"утверждённому распределению VICTOR2.0. "
        f"Подтема «{sub_name}» ({sid}, {order_desc}) соответствует уровню "
        f"школьной программы {grade} класса и может быть использована "
        f"для олимпиадных задач уровня L1-L3."
    )


def compute_scope(grid: dict, taxonomy: dict) -> dict:
    """
    Compute scope metrics:
      - allowed_grade_topic_pairs
      - allowed_grade_topic_subtopic_cells
      - slots_l1, slots_l2, slots_l3
      - expected_tasks_per_level
      - total_expected_tasks
    """
    allowed_pairs = 0
    allowed_cells = 0
    excluded_cells = 0
    grade_breakdown = {}

    for grade_key, grade_data in grid["grades"].items():
        grade = int(grade_key)
        topics = grade_data["topics"]
        g_allowed_subs = 0
        g_excluded_subs = 0
        for tid, tdata in topics.items():
            subs = tdata["subtopics"]
            allowed_count = sum(1 for s in subs.values() if s["allowed"])
            excluded_count = sum(1 for s in subs.values() if not s["allowed"])
            g_allowed_subs += allowed_count
            g_excluded_subs += excluded_count
            if allowed_count > 0:
                allowed_pairs += 1
        allowed_cells += g_allowed_subs
        excluded_cells += g_excluded_subs
        grade_breakdown[grade_key] = {
            "topics": len(topics),
            "allowed_subtopic_cells": g_allowed_subs,
            "excluded_subtopic_cells": g_excluded_subs,
            "slots": g_allowed_subs * len(LEVELS),
            "expected_tasks": g_allowed_subs * len(LEVELS) * TASKS_PER_SLOT
        }

    total_allowed_cells = allowed_cells
    total_slots = total_allowed_cells * len(LEVELS)
    total_tasks = total_slots * TASKS_PER_SLOT

    return {
        "allowed_grade_topic_pairs": allowed_pairs,
        "allowed_grade_topic_subtopic_cells": allowed_cells,
        "excluded_subtopic_cells": excluded_cells,
        "levels_per_cell": len(LEVELS),
        "total_slots": total_slots,
        "slots_l1": total_allowed_cells,
        "slots_l2": total_allowed_cells,
        "slots_l3": total_allowed_cells,
        "tasks_per_slot": TASKS_PER_SLOT,
        "expected_tasks_l1": total_allowed_cells * TASKS_PER_SLOT,
        "expected_tasks_l2": total_allowed_cells * TASKS_PER_SLOT,
        "expected_tasks_l3": total_allowed_cells * TASKS_PER_SLOT,
        "total_expected_tasks": total_tasks,
        "grade_breakdown": grade_breakdown
    }


def build_audit(grid: dict, taxonomy: dict) -> dict:
    scope = compute_scope(grid, taxonomy)
    sha256 = compute_sha256(grid)

    # Verify invariants
    invariants = {}
    # All topic IDs referenced in grades exist in taxonomy
    all_ref_tids = set()
    for grade_data in grid["grades"].values():
        all_ref_tids.update(grade_data["topics"].keys())
    missing_tids = [t for t in all_ref_tids if t not in taxonomy]
    invariants["all_referenced_topics_exist_in_taxonomy"] = len(missing_tids) == 0
    invariants["missing_topic_ids"] = missing_tids

    # All subtopics S0,S1,S2 present for each referenced topic
    missing_subs = []
    for tid in all_ref_tids:
        if tid in taxonomy:
            for sid in ["S0", "S1", "S2"]:
                if sid not in taxonomy[tid]["subtopics"]:
                    missing_subs.append(f"{tid}|{sid}")
    invariants["all_subtopics_s0_s1_s2_present"] = len(missing_subs) == 0
    invariants["missing_subtopic_refs"] = missing_subs

    # Only known levels L1/L2/L3
    invariants["levels_are_L1_L2_L3"] = set(LEVELS) == {"L1", "L2", "L3"}

    # Exclusions documented
    expected_exclusions = len(SUBS_EXCLUDED)
    actual_excluded = scope["excluded_subtopic_cells"]
    invariants["exclusions_matched"] = expected_exclusions == actual_excluded

    all_invariants_pass = all(
        v is True for v in invariants.values()
        if isinstance(v, bool)
    )

    audit = {
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
        "grid_file": "target_grid.json",
        "taxonomy_source": "canonical_taxonomy.json",
        "taxonomy_sha256": None,  # will fill from existing audit
        "grid_sha256": sha256,
        "scope": scope,
        "invariants": invariants,
        "all_invariants_pass": all_invariants_pass,
        "status": "GRID_OK" if all_invariants_pass else "GRID_PARSE_ERROR"
    }
    return audit


def load_taxonomy_sha256() -> str:
    """Load the SHA-256 from the existing taxonomy audit."""
    audit_path = os.path.join(BASE_DIR, "canonical_taxonomy_audit.json")
    if os.path.isfile(audit_path):
        with open(audit_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("sha256")
    return None


def main():
    print("=" * 60)
    print("BUILDING TARGET GRID FROM CANONICAL TAXONOMY")
    print("=" * 60)

    # Load taxonomy
    if not os.path.isfile(TAXONOMY_PATH):
        print(f"[ERR] Taxonomy not found: {TAXONOMY_PATH}")
        sys.exit(1)

    taxonomy = load_taxonomy(TAXONOMY_PATH)
    print(f"[OK] Loaded taxonomy: {len(taxonomy)} topics")

    # Build target grid
    grid = build_grid(taxonomy)
    with open(GRID_PATH, "w", encoding="utf-8") as f:
        json.dump(grid, f, ensure_ascii=False, indent=2)
    print(f"[OK] Created target_grid.json")

    # Build audit
    taxonomy_sha = load_taxonomy_sha256()
    audit = build_audit(grid, taxonomy)
    audit["taxonomy_sha256"] = taxonomy_sha
    with open(AUDIT_PATH, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    print(f"[OK] Created target_grid_audit.json")

    # Print summary
    scope = audit["scope"]
    print()
    print("TARGET GRID SCOPE SUMMARY")
    print(f"  Allowed grade-topic pairs:       {scope['allowed_grade_topic_pairs']}")
    print(f"  Allowed grade-topic-subtopic cells: {scope['allowed_grade_topic_subtopic_cells']}")
    print(f"  Excluded subtopic cells:         {scope['excluded_subtopic_cells']}")
    print(f"  Levels per cell:                 {scope['levels_per_cell']}")
    print(f"  Total slots (all levels):        {scope['total_slots']}")
    print(f"  L1 slots:                        {scope['slots_l1']}")
    print(f"  L2 slots:                        {scope['slots_l2']}")
    print(f"  L3 slots:                        {scope['slots_l3']}")
    print(f"  Tasks per slot:                  {scope['tasks_per_slot']}")
    print(f"  Expected L1 tasks:               {scope['expected_tasks_l1']}")
    print(f"  Expected L2 tasks:               {scope['expected_tasks_l2']}")
    print(f"  Expected L3 tasks:               {scope['expected_tasks_l3']}")
    print(f"  TOTAL expected tasks:            {scope['total_expected_tasks']}")
    print()
    print("Grade breakdown:")
    for gk, gb in scope["grade_breakdown"].items():
        print(f"  Grade {gk}: {gb['topics']} topics, {gb['allowed_subtopic_cells']} cells, "
              f"{gb['slots']} slots, {gb['expected_tasks']} tasks "
              f"({gb['excluded_subtopic_cells']} excluded)")

    print()
    invariants_ok = audit["all_invariants_pass"]
    status = audit["status"]
    print(f"  Invariants: {'ALL PASS' if invariants_ok else 'FAIL'}")
    print(f"  Status: {status}")
    print(f"  SHA-256: {audit['grid_sha256']}")

    if not invariants_ok:
        print("[ERR] Invariant checks failed!")
        for k, v in audit["invariants"].items():
            if isinstance(v, bool) and not v:
                print(f"  ! {k}: {v}")
        sys.exit(1)

    print("\n[DONE] Target grid build complete.")


if __name__ == "__main__":
    main()
