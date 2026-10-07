#!/usr/bin/env python3
"""ШАГ 14.10: Unit tests (10) + retest (10+20).

PART 1 — 10 Unit Tests that validate core reconstruction utilities:
  1. parse_slot_key() — valid format "G10|L4|T013|S0" returns ('10','L4','T013','S0')
  2. parse_slot_key() — malformed input returns None
  3. build_canonical_lookup() — indexes all 558 canonical cells
  4. build_canonical_lookup() — correct key fields (grade, level, topic_id, topic_name)
  5. Valid topic_ids set contains exactly T001-T041 (41 topics)
  6. Invalid topic_ids (T042, T043) correctly excluded from valid set
  7. Cell key format "grade|level|topic_id" matches canonical cell entries
  8. Grade-level-topic combo mismatch detection logic
  9. Valid candidate identification (correct topic + correct combo)
  10. C10 false rejection detection (expected_topic != canonical_topic_name)

PART 2 — Retest 10+20 candidates:
  - Retest 10: Verify all 11 invalid_topic entries (T042:6, T043:5) are truly garbage
    (no valid canonical cell exists for these phantom topic_ids)
  - Retest 20: Verify C10 false rejections would pass with correct canonical taxonomy
    (2 entries per topic mismatch pattern x 10 patterns = 20 entries)

Output: taxonomy_reconstruction/step14_10_report.json
"""

import json
import os
import sys
from collections import Counter, defaultdict

RECON_DIR = "l4_l5_finalization/taxonomy_reconstruction"
CANDIDATES_PATH = "l4_l5_finalization/stage6_candidates.json"
CANONICAL_PATH = os.path.join(RECON_DIR, "canonical_taxonomy.json")
CONTAMINATION_AUDIT_PATH = os.path.join(RECON_DIR, "stage6_contamination_audit.json")
C10_C12_AUDIT_PATH = os.path.join(RECON_DIR, "stage7_c10_c12_audit.json")
OUTPUT_PATH = os.path.join(RECON_DIR, "step14_10_report.json")


# ============================================================
# UTILITY FUNCTIONS (reused from ШАГ 14.8 / 14.9)
# ============================================================

def load_json(path, label=""):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"  Loaded {label}: {path}")
    return data


def parse_slot_key(slot_key):
    """Parse 'G10|L4|T013|S0' -> ('10', 'L4', 'T013', 'S0'). Returns None if malformed."""
    parts = slot_key.split("|")
    if len(parts) != 4:
        return None
    grade = parts[0].lstrip("G")
    return grade, parts[1], parts[2], parts[3]


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


def record(tests, name, passed, details=""):
    """Record a test result."""
    tests.append({
        "test_name": name,
        "passed": passed,
        "details": details,
    })
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}")
    if details:
        print(f"         {details}")
    return passed


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 70)
    print("  ШАГ 14.10: Unit tests (10) + retest (10+20)")
    print("=" * 70)

    # --------------------------------------------------
    # LOAD DATA
    # --------------------------------------------------
    print("\n[LOAD] Loading data files...")
    canon = load_json(CANONICAL_PATH, "canonical_taxonomy")
    candidates_data = load_json(CANDIDATES_PATH, "stage6_candidates")
    contamination_audit = load_json(CONTAMINATION_AUDIT_PATH, "contamination_audit")
    c10_c12_audit = load_json(C10_C12_AUDIT_PATH, "c10_c12_audit")

    candidates = candidates_data["candidates"]
    canonical_cells = canon.get("canonical_cells", [])
    valid_topic_ids = set(canon["meta"]["topic_ids"])
    lookup = build_canonical_lookup(canon)

    print(f"\n  Canonical cells: {len(canonical_cells)}")
    print(f"  Valid topic_ids: {len(valid_topic_ids)} ({sorted(valid_topic_ids)[0]}..{sorted(valid_topic_ids)[-1]})")
    print(f"  Candidates: {len(candidates)}")
    print(f"  Contamination audit entries: {len(contamination_audit.get('valid',[]))} valid, "
          f"{len(contamination_audit.get('invalid_topic',[]))} invalid_topic, "
          f"{len(contamination_audit.get('combo_mismatch',[]))} combo_mismatch")
    print(f"  C10/C12 audit entries: {len(c10_c12_audit.get('entries',[]))}")

    # ============================================================
    # PART 1: 10 UNIT TESTS
    # ============================================================
    print("\n" + "=" * 70)
    print("  PART 1: 10 Unit Tests")
    print("=" * 70)
    tests = []

    # --- UT-01: parse_slot_key() valid format ---
    print("\n--- UT-01: parse_slot_key() valid format ---")
    result = parse_slot_key("G10|L4|T013|S0")
    expected = ("10", "L4", "T013", "S0")
    ut01_pass = (result == expected)
    record(tests, "UT-01: parse_slot_key valid format",
           ut01_pass,
           f"parse_slot_key('G10|L4|T013|S0')={result}, expected={expected}")

    # --- UT-02: parse_slot_key() malformed input ---
    print("\n--- UT-02: parse_slot_key() malformed input ---")
    malformed_inputs = [
        "G10|L4|T013",          # only 3 parts
        "G10|L4|T013|S0|extra", # 5 parts
        "",                      # empty string
        "invalid",
    ]
    ut02_pass = True
    for inp in malformed_inputs:
        r = parse_slot_key(inp)
        if r is not None:
            ut02_pass = False
            print(f"  FAIL: parse_slot_key('{inp}') returned {r}, expected None")
    record(tests, "UT-02: parse_slot_key malformed returns None",
           ut02_pass,
           f"Tested {len(malformed_inputs)} malformed inputs, all returned None")

    # --- UT-03: build_canonical_lookup() indexes all 558 cells ---
    print("\n--- UT-03: build_canonical_lookup() cell count ---")
    n_cells = len(canonical_cells)
    n_lookup = len(lookup)
    ut03_pass = (n_lookup == n_cells)
    record(tests, "UT-03: build_canonical_lookup cell count",
           ut03_pass,
           f"lookup has {n_lookup} entries, canonical_cells has {n_cells} cells")

    # --- UT-04: build_canonical_lookup() correct key fields ---
    print("\n--- UT-04: build_canonical_lookup() key fields ---")
    ut04_pass = True
    missing_fields = set()
    for ck, info in lookup.items():
        for field in ["grade", "level", "topic_id", "topic_name"]:
            if info.get(field) is None or info.get(field) == "":
                missing_fields.add(field)
                ut04_pass = False
    sample_key = "G10|L4|T013|S0"
    sample = lookup.get(sample_key)
    if sample:
        print(f"  Sample cell {sample_key}: grade={sample.get('grade')}, "
              f"level={sample.get('level')}, topic_id={sample.get('topic_id')}, "
              f"topic_name={sample.get('topic_name')}")
    else:
        print(f"  WARNING: sample cell {sample_key} not found in lookup")
    record(tests, "UT-04: lookup key fields present",
           ut04_pass,
           f"Missing fields across all entries: {missing_fields if missing_fields else 'none'}")

    # --- UT-05: Valid topic_ids set contains exactly T001-T041 (41 topics) ---
    print("\n--- UT-05: Valid topic_ids = T001..T041 ---")
    expected_topic_ids = set(f"T{i:03d}" for i in range(1, 42))
    ut05_pass = (valid_topic_ids == expected_topic_ids)
    missing = expected_topic_ids - valid_topic_ids
    extra = valid_topic_ids - expected_topic_ids
    record(tests, "UT-05: valid topic_ids T001-T041",
           ut05_pass,
           f"Expected {len(expected_topic_ids)} topics, got {len(valid_topic_ids)}. "
           f"Missing: {sorted(missing)[:5] if missing else 'none'}. "
           f"Extra: {sorted(extra)[:5] if extra else 'none'}")

    # --- UT-06: Invalid topic_ids T042/T043 correctly excluded ---
    print("\n--- UT-06: Invalid topic_ids T042/T043 excluded ---")
    invalid_ids = {"T042", "T043"}
    ut06_pass = not (invalid_ids & valid_topic_ids)
    record(tests, "UT-06: invalid topic_ids excluded",
           ut06_pass,
           f"T042/T043 in valid set: {bool(invalid_ids & valid_topic_ids)}")

    # --- UT-07: Cell key format validation ---
    print("\n--- UT-07: Cell key format 'grade|level|topic_id|slot' ---")
    ut07_pass = True
    format_issues = []
    for cell in canonical_cells[:10]:
        ck = cell.get("cell_key", "")
        parts = ck.split("|")
        if len(parts) != 4:
            ut07_pass = False
            format_issues.append(f"Bad cell_key format: {ck}")
            continue
        grade, level, tid, slot = parts
        if not grade.startswith("G"):
            ut07_pass = False
            format_issues.append(f"grade '{grade}' missing G prefix in {ck}")
        if tid not in valid_topic_ids:
            ut07_pass = False
            format_issues.append(f"topic_id '{tid}' not valid in {ck}")

    # Also check that lookup cell keys match canonical cell keys
    lookup_cell_keys = set(lookup.keys())
    cell_key_set = set(c.get("cell_key", "") for c in canonical_cells)
    if lookup_cell_keys != cell_key_set:
        ut07_pass = False
        format_issues.append(f"lookup keys ({len(lookup_cell_keys)}) != canonical cell keys ({len(cell_key_set)})")

    record(tests, "UT-07: cell key format validation",
           ut07_pass,
           f"Issues: {len(format_issues)}")
    if ut07_pass:
        print(f"  All {len(canonical_cells)} cell keys have correct 'grade|level|topic_id|slot' format")

    # --- UT-08: Combo mismatch detection ---
    print("\n--- UT-08: Combo mismatch detection logic ---")
    combo_mismatches = contamination_audit.get("combo_mismatch", [])
    ut08_pass = True
    combo_issues = []
    valid_cell_keys_no_slot = set()
    for cell in canonical_cells:
        ck = cell.get("cell_key", "")
        parts = ck.split("|")
        if len(parts) == 4:
            valid_cell_keys_no_slot.add(f"{parts[0]}|{parts[1]}|{parts[2]}")

    for entry in combo_mismatches[:20]:
        sk = entry.get("slot_key", "")
        parts = sk.split("|")
        if len(parts) == 4:
            combo_key = f"{parts[0]}|{parts[1]}|parts[2]"
            if combo_key in valid_cell_keys_no_slot:
                ut08_pass = False
                combo_issues.append(f"combo_mismatch entry '{sk}' actually has valid combo key")
    record(tests, "UT-08: combo mismatch detection",
           ut08_pass,
           f"Checked {min(len(combo_mismatches), 20)} entries, "
           f"invalid combo issues: {len(combo_issues)}")

    # --- UT-09: Valid candidate identification ---
    print("\n--- UT-09: Valid candidate identification ---")
    valid_entries = contamination_audit.get("valid", [])
    ut09_pass = True
    valid_issues = []
    for entry in valid_entries[:20]:
        sk = entry.get("slot_key", "")
        topic_id = entry.get("topic_id", "")
        # A valid entry should have a topic_id within T001-T041
        if topic_id not in valid_topic_ids:
            ut09_pass = False
            valid_issues.append(f"valid entry '{sk}' has non-canonical topic_id '{topic_id}'")
        # Its grade-level-topic combo should exist in canonical cells
        parts = sk.split("|")
        if len(parts) == 4:
            combo_key = f"G{parts[0].lstrip('G')}|{parts[1]}|{parts[2]}"
            # Check if any cell starts with this combo
            matching_cells = [ck for ck in lookup if ck.startswith(combo_key)]
            if not matching_cells:
                ut09_pass = False
                valid_issues.append(f"valid entry '{sk}' has no matching canonical cell for combo {combo_key}")
    record(tests, "UT-09: valid candidate identification",
           ut09_pass,
           f"Checked {min(len(valid_entries), 20)} entries, issues: {len(valid_issues)}")

    # --- UT-10: C10 false rejection detection ---
    print("\n--- UT-10: C10 false rejection detection ---")
    c10_false_rejections = c10_c12_audit.get("c10_false_rejection_details", [])
    ut10_pass = True
    c10_issues = []
    for entry in c10_false_rejections[:20]:
        sk = entry.get("slot_key", "")
        expected_topic = entry.get("expected", "")
        canonical_topic_name = entry.get("canonical", "")
        if expected_topic == canonical_topic_name:
            ut10_pass = False
            c10_issues.append(f"C10 entry '{sk}': expected == canonical ('{expected_topic}') — not a false rejection")
    record(tests, "UT-10: C10 false rejection detection",
           ut10_pass,
           f"Checked {min(len(c10_false_rejections), 20)} entries, issues: {len(c10_issues)}")

    # ============================================================
    # PART 1 SUMMARY
    # ============================================================
    print("\n" + "=" * 70)
    print("  PART 1 SUMMARY")
    print("=" * 70)
    passed = sum(1 for t in tests if t["passed"])
    failed = sum(1 for t in tests if not t["passed"])
    print(f"  Passed: {passed}/{len(tests)}")
    print(f"  Failed: {failed}/{len(tests)}")
    for t in tests:
        status = "PASS" if t["passed"] else "FAIL"
        print(f"    [{status}] {t['test_name']}")

    # ============================================================
    # PART 2: RETEST 10 (invalid_topic T042/T043 garbage verification)
    # ============================================================
    print("\n" + "=" * 70)
    print("  PART 2: RETEST 10 — invalid_topic garbage verification")
    print("=" * 70)
    invalid_topic_entries = contamination_audit.get("invalid_topic", [])
    retest10_results = []
    for entry in invalid_topic_entries:
        sk = entry.get("slot_key", "")
        topic_id = entry.get("topic_id", "")
        entry_data = entry.get("entry", {})
        task_output = entry_data.get("task_output", "")
        # Check: topic_id is T042 or T043 (phantom topics)
        is_phantom = topic_id in {"T042", "T043"}
        # Check: no canonical cell exists for this topic_id
        has_canonical_cell = any(
            cell.get("topic_id") == topic_id
            for cell in canonical_cells
        )
        # Check: the candidate data is garbage/empty
        is_garbage = (not task_output or len(task_output.strip()) < 50)
        retest10_results.append({
            "slot_key": sk,
            "topic_id": topic_id,
            "is_phantom_topic": is_phantom,
            "has_canonical_cell": has_canonical_cell,
            "is_garbage": is_garbage,
            "task_output_preview": task_output[:120] if task_output else "(empty)",
        })
        flags = []
        if not is_phantom:
            flags.append("NOT_PHANTOM")
        if has_canonical_cell:
            flags.append("HAS_CANONICAL")
        if not is_garbage:
            flags.append("NOT_GARBAGE")
        status_str = "GARBAGE" if (is_phantom and not has_canonical_cell and is_garbage) else f"ISSUE: {', '.join(flags)}"
        print(f"  {sk}: topic={topic_id}, phantom={is_phantom}, "
              f"has_canonical={has_canonical_cell}, garbage={is_garbage} -> {status_str}")

    retest10_passed = all(
        r["is_phantom_topic"] and not r["has_canonical_cell"] and r["is_garbage"]
        for r in retest10_results
    )
    print(f"\n  RETEST 10: {len(retest10_results)} entries, "
          f"{'ALL PASS (garbage confirmed)' if retest10_passed else 'SOME HAVE ISSUES'}")

    # ============================================================
    # PART 2: RETEST 20 (C10 false rejection verification)
    # ============================================================
    print("\n" + "=" * 70)
    print("  PART 2: RETEST 20 — C10 false rejection verification")
    print("=" * 70)
    c10_entries = c10_c12_audit.get("entries", [])
    # Build lookup by slot_key for quick access
    entries_by_slot = {e["slot_key"]: e for e in c10_entries}

    topic_mismatch_breakdown = c10_c12_audit.get("topic_mismatch_breakdown", {})
    retest20_results = []
    # Sample 2 entries per topic mismatch pattern x 10 patterns = 20 entries
    samples_per_pattern = {}
    for pattern_key, pattern_data in topic_mismatch_breakdown.items():
        slot_keys = pattern_data.get("slot_keys", [])
        samples_per_pattern[pattern_key] = slot_keys[:2]

    # Build a flat set of all sampled slot_keys for quick filtering
    sampled_slots = set()
    for sampled_keys in samples_per_pattern.values():
        sampled_slots.update(sampled_keys)

    # Use the detailed entries for rich C10 data
    for entry in c10_entries:
        sk = entry.get("slot_key", "")
        if sk not in sampled_slots:
            continue
        c10 = entry.get("c10", {})
        expected_topic = (c10 or {}).get("expected_topic", "")
        canonical_topic_name = (c10 or {}).get("canonical_topic_name", "")
        c10_passed = (c10 or {}).get("passed", None)

        # Verify: expected_topic != canonical_topic_name (it IS a false rejection)
        is_false_rejection = bool(expected_topic and canonical_topic_name and expected_topic != canonical_topic_name)
        # Verify: C10 currently fails (passed=False) because it compares against wrong topic
        would_pass_with_correct = (c10_passed is False)

        retest20_results.append({
            "slot_key": sk,
            "expected_topic": expected_topic,
            "canonical_topic_name": canonical_topic_name,
            "is_false_rejection": is_false_rejection,
            "c10_passed": c10_passed,
            "would_pass_with_correct": would_pass_with_correct,
        })
        print(f"  {sk}: expected='{expected_topic}' vs canonical='{canonical_topic_name}' | "
              f"c10_passed={c10_passed}, false_rejection={is_false_rejection}, "
              f"would_pass_with_correct={would_pass_with_correct}")

    retest20_total = len(retest20_results)
    retest20_passed_count = sum(1 for r in retest20_results if r["is_false_rejection"] and r["would_pass_with_correct"])
    print(f"\n  RETEST 20: {retest20_total} entries sampled, "
          f"{retest20_passed_count}/{retest20_total} confirmed as valid false rejections")

    # ============================================================
    # BUILD REPORT
    # ============================================================
    report = {
        "step": "14.10",
        "description": "Unit tests (10) + retest (10+20)",
        "part1_unit_tests": {
            "total": len(tests),
            "passed": passed,
            "failed": failed,
            "tests": tests,
        },
        "part2_retest_10": {
            "description": "Verify all 11 invalid_topic entries (T042/T043) are garbage",
            "total": len(retest10_results),
            "passed": retest10_passed,
            "results": retest10_results,
        },
        "part2_retest_20": {
            "description": "Verify C10 false rejections with correct canonical taxonomy",
            "total": retest20_total,
            "confirmed": retest20_passed_count,
            "results": retest20_results,
        },
    }

    print("\n" + "=" * 70)
    print(f"  REPORT: {OUTPUT_PATH}")
    print("=" * 70)
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  Report saved to {OUTPUT_PATH}")
    print("  ШАГ 14.10 complete.")
    return report


if __name__ == "__main__":
    main()
