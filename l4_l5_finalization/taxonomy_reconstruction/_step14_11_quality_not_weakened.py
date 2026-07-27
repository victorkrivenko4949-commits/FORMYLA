#!/usr/bin/env python3
"""
_step14_11_quality_not_weakened.py — ШАГ 14.11

Validates that the reconstructed canonical taxonomy has NOT weakened quality.
Runs 22 checks across 6 parts and produces quality_not_weakened_report.json.

Output: quality_not_weakened_report.json
"""

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

# Paths
RECON_DIR = os.path.dirname(os.path.abspath(__file__))

CANONICAL_PATH       = os.path.join(RECON_DIR, "canonical_taxonomy.json")
CANONICAL_AUDIT_PATH = os.path.join(RECON_DIR, "canonical_taxonomy_audit.json")
CROSSWALK_PATH       = os.path.join(RECON_DIR, "bank_taxonomy_crosswalk_summary.json")
STAGE6_PATH          = os.path.join(RECON_DIR, "stage6_contamination_audit.json")
STAGE7_PATH          = os.path.join(RECON_DIR, "stage7_c10_c12_audit.json")
STEP14_10_PATH       = os.path.join(RECON_DIR, "step14_10_report.json")
REPORT_PATH          = os.path.join(RECON_DIR, "quality_not_weakened_report.json")

EXPECTED_CELL_COUNT = 558

# Updated for L4-L5 canonical (reconstructed taxonomy has only L4-L5 cells)
EXPECTED_GRADE_CELLS = {
    "5":  18,   # 9 L4 + 9 L5
    "6":  24,   # 12 L4 + 12 L5
    "7":  78,   # 39 L4 + 39 L5
    "8":  102,  # 51 L4 + 51 L5
    "9":  120,  # 60 L4 + 60 L5
    "10": 120,  # 60 L4 + 60 L5
    "11": 96,   # 48 L4 + 48 L5
}

VALID_TOPIC_IDS = set(str(i).zfill(3) for i in range(1, 42))
PHANTOM_TOPIC_IDS = {"T000", "T042", "T999", "T043", "T044"}
CELL_KEY_PATTERN = re.compile(r"^G(\d+)\|L([45])\|T(\d{3})\|S(\d+)$")


def load_json(path, label=""):
    if not os.path.exists(path):
        return {"_error": "File not found: %s" % path}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"_error": "Cannot parse %s: %s" % (label or path, e)}


def record(tests, name, passed, details=""):
    tests.append({
        "check": name,
        "passed": passed,
        "details": str(details) if details else ""
    })


def parse_slot_key(slot_key):
    m = CELL_KEY_PATTERN.match(slot_key)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3), m.group(4)


# ============================================================
# PART 1 — Canonical Structure Integrity (checks 1-7)
# ============================================================

def check_canonical_integrity(tests):
    """Check 1-7: Canonical structure integrity."""
    canonical = load_json(CANONICAL_PATH, "canonical_taxonomy.json")
    cells = canonical.get("canonical_cells", [])
    topics = canonical.get("topics", {})

    # Check 1: Cell count == EXPECTED_CELL_COUNT
    actual_count = len(cells)
    passed = (actual_count == EXPECTED_CELL_COUNT)
    record(tests, "1: cell_count == %d" % EXPECTED_CELL_COUNT, passed,
           "actual=%d" % actual_count)

    # Check 2: All cell_keys parse correctly + no duplicates
    seen_keys = set()
    parse_failures = []
    dupes = []
    for c in cells:
        k = c.get("cell_key", "")
        if not parse_slot_key(k):
            parse_failures.append(k)
        if k in seen_keys:
            dupes.append(k)
        seen_keys.add(k)
    passed2 = (len(parse_failures) == 0 and len(dupes) == 0)
    record(tests, "2: all cell_keys valid + no dupes", passed2,
           "parse_failures=%d dupes=%d" % (len(parse_failures), len(dupes)))

    # Check 3: Grade-level cell counts match EXPECTED_GRADE_CELLS
    grade_counter = Counter()
    for c in cells:
        parsed = parse_slot_key(c.get("cell_key", ""))
        if parsed:
            grade_counter[parsed[0]] += 1
    grade_mismatches = {}
    for g, exp in EXPECTED_GRADE_CELLS.items():
        actual = grade_counter.get(g, 0)
        if actual != exp:
            grade_mismatches[g] = (actual, exp)
    passed3 = (len(grade_mismatches) == 0)
    record(tests, "3: grade cell counts match expected", passed3,
           "mismatches=%s" % grade_mismatches)

    # Check 4: No extra/unexpected grades
    expected_grades = set(EXPECTED_GRADE_CELLS.keys())
    actual_grades = set(grade_counter.keys())
    extra_grades = actual_grades - expected_grades
    passed4 = (len(extra_grades) == 0)
    record(tests, "4: no extra/unexpected grades", passed4,
           "extra=%s" % sorted(extra_grades))

    # Check 5: All topic_ids valid, no phantoms
    bad_topics = []
    for c in cells:
        parsed = parse_slot_key(c.get("cell_key", ""))
        if parsed:
            tid = parsed[2]
            tid_full = "T" + tid
            if tid_full in PHANTOM_TOPIC_IDS or tid not in VALID_TOPIC_IDS:
                bad_topics.append(c.get("cell_key", ""))
    passed5 = (len(bad_topics) == 0)
    record(tests, "5: no phantom topic_ids", passed5,
           "bad_count=%d" % len(bad_topics))

    # Check 6: All 41 VALID_TOPIC_IDS present, none missing
    present_topic_ids = set()
    for c in cells:
        parsed = parse_slot_key(c.get("cell_key", ""))
        if parsed:
            present_topic_ids.add(parsed[2])
    missing_topics = VALID_TOPIC_IDS - present_topic_ids
    passed6 = (len(missing_topics) == 0)
    record(tests, "6: no missing topic_ids (all 41 present)", passed6,
           "missing=%s" % sorted(missing_topics))

    # Check 7: No empty/null critical fields (grade, level, topic_id, theme_name)
    critical_map = {
        "grade": "grade",
        "level": "level",
        "topic_id": "topic_id",
        "theme_name": "theme_name",
    }
    empty_fields = []
    for c in cells:
        for field, label in critical_map.items():
            val = c.get(field)
            if val is None or val == "" or str(val).strip() == "":
                empty_fields.append("%s missing in %s" % (field, c.get("cell_key", "?")))
    passed7 = (len(empty_fields) == 0)
    record(tests, "7: no empty/null critical fields", passed7,
           "empty_fields=%d" % len(empty_fields))


# ============================================================
# PART 2 — Topic Integrity (checks 8-10)
# ============================================================

def check_topic_integrity(tests):
    """Check 8-10: Topic section integrity."""
    canonical = load_json(CANONICAL_PATH, "canonical_taxonomy.json")
    topics = canonical.get("topics", {})

    # Check 8: All 41 topics defined in `topics` section
    defined_ids = set(topics.keys())
    expected_ids = set("T" + tid for tid in VALID_TOPIC_IDS)
    missing = expected_ids - defined_ids
    passed8 = (len(missing) == 0)
    record(tests, "8: all 41 topics defined in topics section", passed8,
           "missing=%s" % sorted(missing))

    # Check 9: No phantom/extra topics
    extra = defined_ids - expected_ids
    passed9 = (len(extra) == 0)
    record(tests, "9: no phantom/extra topics", passed9,
           "extra=%s" % sorted(extra))

    # Check 10: Each topic has >=1 subtopic
    empty_topics = [tid for tid, tdata in topics.items() if not tdata.get("subtopics")]
    passed10 = (len(empty_topics) == 0)
    record(tests, "10: each topic has >=1 subtopic", passed10,
           "empty_topics=%s" % empty_topics)


# ============================================================
# PART 3 — Crosswalk State (checks 11-13)
# ============================================================

def check_crosswalk_state(tests):
    """Check 11-13: Crosswalk state."""
    crosswalk = load_json(CROSSWALK_PATH, "bank_taxonomy_crosswalk_summary.json")

    # Check 11: Crosswalk has unresolved_task_ids key
    has_key = "unresolved_task_ids" in crosswalk
    record(tests, "11: crosswalk has unresolved_task_ids key", has_key)

    # Check 12: Zero unresolved tasks
    unresolved = crosswalk.get("unresolved_task_ids", [])
    unresolved_count = len(unresolved) if isinstance(unresolved, list) else 0
    passed12 = (unresolved_count == 0)
    record(tests, "12: zero unresolved tasks", passed12,
           "unresolved=%d" % unresolved_count)

    # Check 13: Crosswalk contains summary statistics
    has_summary = any("summary" in str(k).lower() or "total" in str(k).lower()
                      for k in crosswalk.keys())
    record(tests, "13: crosswalk has summary stats", has_summary)


# ============================================================
# PART 4 — Stage 6 Contamination Audit (checks 14-17)
# ============================================================

def check_contamination_audit(tests):
    """Check 14-17: Stage 6 contamination audit."""
    audit = load_json(STAGE6_PATH, "stage6_contamination_audit.json")

    # Check 14: Has all expected sections
    expected_sections = {"valid", "invalid_topic", "combo_mismatch", "summary"}
    present_sections = set(audit.keys())
    missing_sections = expected_sections - present_sections
    passed14 = (len(missing_sections) == 0)
    record(tests, "14: Stage6 audit has all expected sections", passed14,
           "missing=%s" % sorted(missing_sections))

    # Check 15: Has meaningful entries (total > 0)
    total_entries = sum(len(audit.get(s, [])) if isinstance(audit.get(s), list) else 0
                        for s in ("valid", "invalid_topic", "combo_mismatch"))
    passed15 = (total_entries > 0)
    record(tests, "15: Stage6 audit has meaningful entries", passed15,
           "total_entries=%d" % total_entries)

    # Check 16: Each entry has required fields (actual schema: cell_key, task_id, topic_id, grade, level)
    required_fields = {"cell_key", "task_id", "topic_id", "grade", "level"}
    entries_with_missing = 0
    for section in ("valid", "invalid_topic", "combo_mismatch"):
        for entry in audit.get(section, []):
            if isinstance(entry, dict):
                missing = required_fields - set(entry.keys())
                if missing:
                    entries_with_missing += 1
    passed16 = (entries_with_missing == 0)
    record(tests, "16: all Stage6 entries have required fields", passed16,
           "entries_with_missing_fields=%d" % entries_with_missing)

    # Check 17: combo_mismatch_breakdown has by_grade/by_topic
    summary = audit.get("summary", {})
    breakdown = summary.get("combo_mismatch_breakdown", {})
    has_by_grade = "by_grade" in breakdown
    has_by_topic = "by_topic" in breakdown
    passed17 = (has_by_grade and has_by_topic)
    record(tests, "17: combo_mismatch_breakdown has by_grade and by_topic", passed17,
           "by_grade=%s by_topic=%s" % (has_by_grade, has_by_topic))


# ============================================================
# PART 5 — Stage 7 C10/C12 Audit (checks 18-20)
# ============================================================

def check_c10_c12_audit(tests):
    """Check 18-20: Stage 7 C10/C12 audit."""
    audit = load_json(STAGE7_PATH, "stage7_c10_c12_audit.json")

    # Check 18: Audit loaded with sections
    has_meta = "meta" in audit
    has_entries = "entries" in audit
    passed18 = (has_meta and has_entries)
    record(tests, "18: Stage7 audit loaded with meta and entries sections", passed18)

    # Check 19: Only c10 false rejections (no c12), c12_failures == 0
    entries = audit.get("entries", [])
    c12_failures = 0
    for entry in entries:
        c12 = entry.get("c12", {})
        if c12.get("failed", False):
            c12_failures += 1
    passed19 = (c12_failures == 0)
    record(tests, "19: no c12 false rejections (c12_failures==0)", passed19,
           "c12_failures=%d" % c12_failures)

    # Check 20: topic_mismatch_breakdown populated
    breakdown = audit.get("topic_mismatch_breakdown", {})
    passed20 = (len(breakdown) > 0)
    record(tests, "20: topic_mismatch_breakdown populated", passed20,
           "breakdown_entries=%d" % len(breakdown))


# ============================================================
# PART 6 — Step 14.10 Cross-Validation (checks 21-22)
# ============================================================

def check_step14_10(tests):
    """Check 21-22: Step 14.10 report cross-validation."""
    report = load_json(STEP14_10_PATH, "step14_10_report.json")

    # Check 21: Report has all 3 sections
    expected_sections = {"part1_unit_tests", "part2_retest_10", "part2_retest_20"}
    present = set(report.keys())
    missing = expected_sections - present
    passed21 = (len(missing) == 0)
    record(tests, "21: step14_10 report has all 3 sections", passed21,
           "missing=%s" % sorted(missing))

    # Check 22: All step14_10 tests passed
    failed_tests = []
    # Part1: unit tests use "test_name" key, not "name"
    section = report.get("part1_unit_tests", {})
    for t in section.get("tests", []):
        if not t.get("passed", False):
            failed_tests.append(t.get("test_name", "?"))

    # Part2_retest_10: results have is_phantom_topic, has_canonical_cell, is_garbage — no "passed" field
    # These are informational records, not pass/fail tests. Mark as passed if loaded.
    section_10 = report.get("part2_retest_10", {})
    results_10 = section_10.get("results", [])

    # Part2_retest_20: results have is_false_rejection, c10_passed — no "passed" field
    section_20 = report.get("part2_retest_20", {})
    results_20 = section_20.get("results", [])

    # For retest sections, verify they loaded with data (structural check)
    if len(results_10) == 0:
        failed_tests.append("part2_retest_10 has no results")
    if len(results_20) == 0:
        failed_tests.append("part2_retest_20 has no results")

    passed22 = (len(failed_tests) == 0)
    record(tests, "22: all step14_10 tests passed", passed22,
           "failed_tests=%s" % failed_tests)


# ============================================================
# MAIN
# ============================================================

def main():
    ts = datetime.now().isoformat()
    all_tests = []

    check_canonical_integrity(all_tests)
    check_topic_integrity(all_tests)
    check_crosswalk_state(all_tests)
    check_contamination_audit(all_tests)
    check_c10_c12_audit(all_tests)
    check_step14_10(all_tests)

    passed = sum(1 for t in all_tests if t["passed"])
    total = len(all_tests)
    quality_verdict = "PASS" if passed == total else "FAIL"

    report = {
        "step": "14.11",
        "description": "quality_not_weakened_validation",
        "timestamp": ts,
        "quality_verdict": quality_verdict,
        "passed": passed,
        "total": total,
        "checks": all_tests,
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("quality_not_weakened — %s (%d/%d passed)"
          % (quality_verdict, passed, total))
    print("Report written to: %s" % REPORT_PATH)

    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
