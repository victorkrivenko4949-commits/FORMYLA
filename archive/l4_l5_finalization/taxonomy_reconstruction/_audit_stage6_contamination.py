#!/usr/bin/env python3
"""ШАГ 14.8: Audit Stage 6 contamination.

Checks every Stage 6 candidate slot key against the canonical taxonomy to find:
1. Invalid topic_ids (phantom topics like T042, T043)
2. Grade-level-topic combos that don't exist in canonical
3. Candidates that need reassignment due to mapping changes
4. Candidates that are orphans (no valid cell in canonical)
"""

import json
import os
from collections import Counter, defaultdict

RECON_DIR = "l4_l5_finalization/taxonomy_reconstruction"
CANDIDATES_PATH = "l4_l5_finalization/stage6_candidates.json"
CANONICAL_PATH = os.path.join(RECON_DIR, "canonical_taxonomy.json")
OUTPUT_PATH = os.path.join(RECON_DIR, "stage6_contamination_audit.json")


def load_json(path, label=""):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"  Loaded {label}: {path}")
    return data


def main():
    print("=" * 70)
    print("ШАГ 14.8: AUDIT STAGE 6 CONTAMINATION")
    print("=" * 70)

    print("\n[1/5] Loading data...")
    candidates_data = load_json(CANDIDATES_PATH, "stage6_candidates")
    canon = load_json(CANONICAL_PATH, "canonical_taxonomy")
    candidates = candidates_data["candidates"]
    print(f"  Total Stage 6 candidates: {len(candidates)}")

    print("\n[2/5] Building canonical lookup structures...")
    valid_cell_keys = set()
    cell_info = {}
    for cell in canon["canonical_cells"]:
        ck = f"{cell['grade']}|{cell['level']}|{cell['topic_id']}"
        valid_cell_keys.add(ck)
        cell_info[ck] = {
            "grade": cell["grade"],
            "level": cell["level"],
            "topic_id": cell["topic_id"],
            "topic_name": cell.get("topic_name", ""),
        }
    valid_topic_ids = set(canon["meta"]["topic_ids"])
    print(f"  Valid canonical cells: {len(valid_cell_keys)}")
    print(f"  Valid topic_ids (T001-T041): {len(valid_topic_ids)}")

    # Build grade-level-topic lookup per topic
    topic_cells = defaultdict(list)  # topic_id -> list of (grade, level) combos
    for cell in canon["canonical_cells"]:
        topic_cells[cell["topic_id"]].append((cell["grade"], cell["level"]))

    print("\n[3/5] Auditing each candidate slot key...")
    results = {
        "valid": [],
        "invalid_topic": [],
        "combo_mismatch": [],
        "summary": {}
    }

    for slot_key, candidate_data in candidates.items():
        parsed = parse_slot_key(slot_key)
        if not parsed:
            results["invalid_topic"].append({
                "slot_key": slot_key,
                "task_id": candidate_data.get("task_id", "?"),
                "reason": "unparseable slot_key"
            })
            continue

        grade, level, topic_id, slot_num = parsed
        entry = {
            "slot_key": slot_key,
            "cell_key": f"{grade}|{level}|{topic_id}",
            "task_id": candidate_data.get("task_id", "?"),
            "grade": grade,
            "level": level,
            "topic_id": topic_id,
            "triple_index": candidate_data.get("triple_index", 0),
            "quality_score": candidate_data.get("quality_score", 0),
            "generation_time": candidate_data.get("generation_time", "?"),
        }

        # Check 1: Is topic_id valid?
        if topic_id not in valid_topic_ids:
            results["invalid_topic"].append(entry)
            continue

        # Check 2: Does the grade-level-topic combo exist in canonical?
        cell_key = f"{grade}|{level}|{topic_id}"
        if cell_key not in valid_cell_keys:
            results["combo_mismatch"].append(entry)
            continue

        # Valid
        results["valid"].append(entry)

    print(f"\n[4/5] Analyzing results...")
    total = len(candidates)
    n_valid = len(results["valid"])
    n_invalid_topic = len(results["invalid_topic"])
    n_combo_mismatch = len(results["combo_mismatch"])

    print(f"\n{'='*70}")
    print(f"  VALID candidates:          {n_valid:4d} ({n_valid/total*100:.1f}%)")
    print(f"  INVALID TOPIC:             {n_invalid_topic:4d} ({n_invalid_topic/total*100:.1f}%)")
    print(f"  COMBO MISMATCH:            {n_combo_mismatch:4d} ({n_combo_mismatch/total*100:.1f}%)")
    print(f"  TOTAL:                     {total:4d}")
    print(f"{'='*70}")

    # Detailed analysis of invalid topics
    if n_invalid_topic > 0:
        invalid_topic_ids = Counter()
        for e in results["invalid_topic"]:
            invalid_topic_ids[e["topic_id"]] += 1
        print(f"\n  Invalid topic_id breakdown:")
        for tid, cnt in invalid_topic_ids.most_common():
            print(f"    {tid}: {cnt} candidates")

    if n_combo_mismatch > 0:
        combo_grades = Counter()
        combo_levels = Counter()
        combo_topics = Counter()
        for e in results["combo_mismatch"]:
            combo_grades[e["grade"]] += 1
            combo_levels[e["level"]] += 1
            combo_topics[e["topic_id"]] += 1
        print(f"\n  Combo mismatch by grade:")
        for g, cnt in sorted(combo_grades.items()):
            print(f"    Grade {g}: {cnt} candidates")
        print(f"\n  Combo mismatch by topic:")
        for t, cnt in combo_topics.most_common(10):
            print(f"    {t}: {cnt} candidates")

    # Build valid cells cross-reference
    valid_cell_slots = Counter()
    for e in results["valid"]:
        valid_cell_slots[e["cell_key"]] += 1

    print(f"\n  Valid candidates cover {len(valid_cell_slots)} unique cells")
    for cell_key, cnt in valid_cell_slots.most_common(10):
        print(f"    {cell_key}: {cnt} candidates")

    # Build summary
    results["summary"] = {
        "total_candidates": total,
        "valid_count": n_valid,
        "invalid_topic_count": n_invalid_topic,
        "combo_mismatch_count": n_combo_mismatch,
        "valid_cells_covered": len(valid_cell_slots),
        "invalid_topic_breakdown": dict(invalid_topic_ids.most_common()) if n_invalid_topic > 0 else {},
        "combo_mismatch_breakdown": {
            "by_grade": dict(sorted(combo_grades.items())),
            "by_topic": dict(combo_topics.most_common(20))
        } if n_combo_mismatch > 0 else {},
    }

    print(f"\n[5/5] Saving audit results to {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"  Saved!")


def parse_slot_key(slot_key):
    parts = slot_key.split("|")
    if len(parts) != 4:
        return None
    # Strip "G" prefix from grade (e.g., "G10" -> "10") to match canonical format
    grade = parts[0].lstrip("G")
    return grade, parts[1], parts[2], parts[3]


if __name__ == "__main__":
    main()
