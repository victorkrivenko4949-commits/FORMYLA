#!/usr/bin/env python3
"""
ШАГ 14.9: Re-audit Stage 7 C10/C12 conditions against canonical taxonomy.

For each rejected Stage 7 entry, checks:
  - C10 (topic_match): whether expected_topic matches canonical topic name
  - C12 (duplicate_check): whether duplicate flag was a false positive
  - All conditions: what specifically caused rejection

Categorization:
  - "c10_false_rejection": expected_topic != canonical topic name
  - "c12_false_rejection": C12 flagged but max_similarity < threshold
  - "c10_c12_both_false": Both C10 and C12 mis-fires
  - "still_valid_rejection": C10/C12 agree with canonical taxonomy
  - "other_reasons": rejected due to c01-c09 or c11 (not C10/C12 related)

Usage:
    python _audit_stage7_c10_c12.py
"""

import json
import os
import sys
from collections import defaultdict, OrderedDict


def load_json(path, label=""):
    if not os.path.exists(path):
        print(f"  ERROR: {label} file not found: {path}")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError as e:
        print(f"  ERROR: Invalid JSON in {label}: {e}")
        return None


def build_canonical_lookup(canonical):
    """Build lookup: cell_key -> {grade, level, topic_id, topic_name, ...}"""
    lookup = {}
    topic_names = {}
    for tid, tinfo in canonical.get("topics", {}).items():
        topic_names[tid] = tinfo.get("name", "")
    for cell in canonical.get("canonical_cells", []):
        ck = cell.get("cell_key", "")
        tid = cell.get("topic_id", "")
        lookup[ck] = {
            "grade": cell.get("grade"),
            "level": cell.get("level"),
            "topic_id": tid,
            "topic_name": topic_names.get(tid, ""),
            "subtopic_name": cell.get("subtopic_name", ""),
            "theme_name": cell.get("theme_name", ""),
        }
    return lookup


def analyze_entry(slot_key, entry, canonical_lookup, canonical):
    """Analyze a single rejected Stage 7 entry and return audit result dict."""
    conditions = entry.get("conditions", {})
    c10 = conditions.get("c10_topic_match", {})
    c12 = conditions.get("c12_duplicate_check", {})

    # --- Parse slot_key ---
    parts = slot_key.split("|")
    if len(parts) != 4:
        return {"slot_key": slot_key, "error": f"Cannot parse slot_key: {slot_key}"}
    grade, level, topic_id, slot_num = parts

    # --- Find canonical cell ---
    canonical_cell = canonical_lookup.get(slot_key, None)

    # --- Get canonical topic name ---
    canonical_topic_name = ""
    canonical_topic_id = topic_id
    if canonical_cell:
        canonical_topic_name = canonical_cell.get("topic_name", "")
        canonical_topic_id = canonical_cell.get("topic_id", topic_id)
    else:
        # Try lookup by topic_id directly
        topic_info = canonical.get("topics", {}).get(topic_id, {})
        canonical_topic_name = topic_info.get("name", "")

    # --- C10 analysis ---
    c10_data = c10.get("data", {})
    expected_topic = c10_data.get("expected_topic", "")
    classifier_topic = c10_data.get("classifier_topic", "")
    c10_topic_match = c10_data.get("topic_match", c10.get("passed", False))
    c10_passed = c10.get("passed", True)
    c10_details = c10.get("details", "")

    # Determine if expected_topic matches canonical topic name
    expected_matches_canonical = False
    if expected_topic and canonical_topic_name:
        # Normalize for comparison (lowercase, strip whitespace)
        exp_norm = expected_topic.lower().strip()
        can_norm = canonical_topic_name.lower().strip()
        expected_matches_canonical = (exp_norm == can_norm)

    # --- C12 analysis ---
    c12_data = c12.get("data", {})
    max_similarity = c12_data.get("max_similarity", 0.0)
    duplicate_of = c12_data.get("duplicate_of", None)
    threshold = c12_data.get("threshold", 0.6)
    c12_passed = c12.get("passed", True)
    c12_details = c12.get("details", "")

    # Determine if C12 was a false positive
    c12_false_positive = False
    if not c12_passed:
        # C12 failed - check if it was a real duplicate
        if duplicate_of is None and max_similarity < threshold:
            c12_false_positive = True

    # --- Collect ALL failed conditions ---
    failed_conditions = []
    passed_conditions = []
    missing_conditions = []
    for cname, cdata in conditions.items():
        if cdata.get("passed", False):
            passed_conditions.append(cname)
        else:
            failed_conditions.append(cname)

    # --- Determine primary rejection category ---
    c10_false = (not c10_passed) and (not expected_matches_canonical) and bool(expected_topic) and bool(canonical_topic_name)
    c12_false = (not c12_passed) and c12_false_positive

    if c10_false and c12_false:
        category = "c10_c12_both_false"
    elif c10_false:
        category = "c10_false_rejection"
    elif c12_false:
        category = "c12_false_rejection"
    else:
        # Check if C10/C12 were the only failures vs other conditions failed
        non_c10_c12_failed = [c for c in failed_conditions
                              if c not in ("c10_topic_match", "c12_duplicate_check")]
        if len(non_c10_c12_failed) == 0 and len(failed_conditions) > 0:
            # Only C10 and/or C12 failed, and they are not false
            category = "still_valid_rejection"
        elif len(failed_conditions) == 0:
            category = "no_failed_conditions"  # shouldn't happen for rejected entries
        else:
            category = "other_reasons"

    # --- Build result ---
    result = OrderedDict()
    result["slot_key"] = slot_key
    result["category"] = category
    result["canonical_cell_found"] = canonical_cell is not None
    result["failed_conditions"] = failed_conditions
    result["passed_conditions"] = passed_conditions

    # C10 details
    result["c10"] = {
        "passed": c10_passed,
        "expected_topic": expected_topic,
        "canonical_topic_name": canonical_topic_name,
        "classifier_topic": classifier_topic,
        "expected_matches_canonical": expected_matches_canonical,
        "topic_match": c10_topic_match,
        "details": c10_details,
    }

    # C12 details
    result["c12"] = {
        "passed": c12_passed,
        "max_similarity": max_similarity,
        "duplicate_of": duplicate_of,
        "threshold": threshold,
        "false_positive": c12_false_positive,
        "details": c12_details,
    }

    # Canonical cell info
    if canonical_cell:
        result["canonical_cell"] = {
            "grade": canonical_cell.get("grade"),
            "level": canonical_cell.get("level"),
            "topic_id": canonical_cell.get("topic_id"),
            "topic_name": canonical_cell.get("topic_name"),
            "subtopic_name": canonical_cell.get("subtopic_name"),
            "theme_name": canonical_cell.get("theme_name"),
        }
    else:
        result["canonical_cell"] = None

    return result


def main():
    print("=" * 70)
    print("  ШАГ 14.9: Re-audit Stage 7 C10/C12 against canonical taxonomy")
    print("=" * 70)

    # Load data
    print("\nLoading checkpoint data...")
    checkpoint = load_json(CHECKPOINT_PATH, "checkpoint")
    if checkpoint is None:
        sys.exit(1)

    print("\nLoading canonical taxonomy...")
    canonical = load_json(CANONICAL_PATH, "canonical")
    if canonical is None:
        sys.exit(1)

    # Build canonical lookup
    print("\nBuilding canonical cell lookup...")
    canonical_lookup = build_canonical_lookup(canonical)
    print(f"  Canonical cells indexed: {len(canonical_lookup)}")

    # Analyze each rejected entry
    rejected = checkpoint.get("rejected", {})
    print(f"\nAnalyzing {len(rejected)} rejected entries...\n")

    results = []
    category_counts = defaultdict(int)
    topic_mismatch_details = defaultdict(list)
    c10_false_details = []
    c12_false_details = []

    for slot_key, entry in rejected.items():
        result = analyze_entry(slot_key, entry, canonical_lookup, canonical)
        results.append(result)
        category_counts[result["category"]] += 1

        # Collect C10 false rejection details
        if result["category"] in ("c10_false_rejection", "c10_c12_both_false"):
            c10 = result["c10"]
            mismatch_key = f"{c10['expected_topic']} -> {c10['canonical_topic_name']}"
            topic_mismatch_details[mismatch_key].append(slot_key)
            c10_false_details.append({
                "slot_key": slot_key,
                "expected": c10["expected_topic"],
                "canonical": c10["canonical_topic_name"],
                "classifier": c10["classifier_topic"],
            })

        # Collect C12 false positive details
        if result["category"] in ("c12_false_rejection", "c10_c12_both_false"):
            c12_false_details.append({
                "slot_key": slot_key,
                "max_similarity": result["c12"]["max_similarity"],
                "threshold": result["c12"]["threshold"],
            })

    # --- Summary ---
    print("=" * 70)
    print("  AUDIT SUMMARY")
    print("=" * 70)
    print(f"\n  Total rejected entries: {len(results)}")

    categories = [
        ("c10_false_rejection", "C10 false rejection (old taxonomy wrong topic)"),
        ("c12_false_rejection", "C12 false positive (not actually duplicate)"),
        ("c10_c12_both_false", "Both C10 and C12 false"),
        ("still_valid_rejection", "C10/C12 still valid rejection"),
        ("other_reasons", "Rejected for other reasons (c01-c09, c11)"),
    ]

    for cat_key, cat_label in categories:
        count = category_counts.get(cat_key, 0)
        pct = (count / len(results)) * 100 if results else 0
        print(f"    {cat_label}: {count} ({pct:.1f}%)")

    # C10 false rejection details
    if c10_false_details:
        print(f"\n  C10 FALSE REJECTIONS (expected_topic != canonical topic):")
        print(f"    Total: {len(c10_false_details)}")
        for mismatch, slots in sorted(topic_mismatch_details.items(),
                                       key=lambda x: -len(x[1])):
            print(f"    {mismatch}: {len(slots)} entries")
            for s in slots:
                print(f"      - {s}")

    # C12 false positive details
    if c12_false_details:
        print(f"\n  C12 FALSE POSITIVES:")
        print(f"    Total: {len(c12_false_details)}")
        for detail in c12_false_details:
            print(f"    - {detail['slot_key']}: "
                  f"max_similarity={detail['max_similarity']:.3f}, "
                  f"threshold={detail['threshold']}")

    # --- Save output ---
    output = {
        "meta": {
            "description": "Stage 7 C10/C12 re-audit against canonical taxonomy",
            "total_rejected": len(results),
        },
        "category_summary": dict(category_counts),
        "c10_false_rejection_details": c10_false_details,
        "c12_false_positive_details": c12_false_details,
        "topic_mismatch_breakdown": {
            k: {"count": len(v), "slot_keys": v}
            for k, v in sorted(topic_mismatch_details.items(),
                               key=lambda x: -len(x[1]))
        },
        "entries": results,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved to: {OUTPUT_PATH}")

    print("\n" + "=" * 70)
    print("  Done.")
    print("=" * 70)


if __name__ == "__main__":
    # Resolve paths using script location
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_DIR = os.path.dirname(BASE_DIR)
    CHECKPOINT_PATH = os.path.join(PROJECT_DIR, "stage7_checkpoint.json")
    CANONICAL_PATH = os.path.join(BASE_DIR, "canonical_taxonomy.json")
    OUTPUT_PATH = os.path.join(BASE_DIR, "stage7_c10_c12_audit.json")
    main()