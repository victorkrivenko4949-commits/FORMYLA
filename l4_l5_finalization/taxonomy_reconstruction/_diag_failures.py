#!/usr/bin/env python3
"""Diagnose the 5 failed quality checks."""
import json, os, re
from collections import Counter

RECON_DIR = os.path.dirname(os.path.abspath(__file__))

def load_json(path, label=""):
    p = os.path.join(RECON_DIR, path)
    if not os.path.exists(p):
        print(f"  MISSING: {label} at {p}")
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def parse_slot_key(slot_key):
    m = re.match(r"^G(\d+)\|L(\d+)\|T(\d+)\|S(\d+)$", str(slot_key))
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
    return None

# ============================================================
# FAILURE 1: Check 3 - Grade cell counts mismatch
# ============================================================
print("=" * 60)
print("FAILURE 1: Check 3 - Grade cell counts mismatch")
print("=" * 60)
canon = load_json("canonical_taxonomy.json", "canonical")
if canon:
    cells = canon.get("canonical_cells", [])
    print(f"  Total cells: {len(cells)}")
    grade_counter = Counter()
    for c in cells:
        parsed = parse_slot_key(c.get("cell_key", ""))
        if parsed:
            grade_counter[parsed[0]] += 1
    for g in sorted(grade_counter.keys()):
        print(f"  Grade {g}: {grade_counter[g]} cells")
    
    # Check levels per grade
    level_counter = Counter()
    for c in cells:
        parsed = parse_slot_key(c.get("cell_key", ""))
        if parsed:
            level_counter[(parsed[0], parsed[1])] += 1
    print("\n  Cells per (grade, level):")
    for gl in sorted(level_counter.keys()):
        print(f"    G{gl[0]}|L{gl[1]}: {level_counter[gl]}")

# ============================================================
# FAILURE 2: Check 7 - Empty critical fields
# ============================================================
print("\n" + "=" * 60)
print("FAILURE 2: Check 7 - Empty/null critical fields")
print("=" * 60)
if canon:
    cells = canon.get("canonical_cells", [])
    critical_fields = ["subject", "topic_name", "level"]
    empty_count = 0
    field_empty_counts = {f: 0 for f in critical_fields}
    sample_empty = []
    for c in cells:
        ck = c.get("cell_key", "?")
        for f in critical_fields:
            val = c.get(f)
            if val is None or val == "" or val == "null":
                field_empty_counts[f] += 1
                empty_count += 1
                if len(sample_empty) < 5:
                    sample_empty.append((ck, f, val))
    print(f"  Total empty fields: {empty_count}")
    for f in critical_fields:
        print(f"  '{f}' empty: {field_empty_counts[f]}")
    for ck, f, val in sample_empty:
        print(f"  Sample: cell_key={ck}, field='{f}', value='{val}'")
    
    # Also check if critical fields even exist in cells
    sample_cell = cells[0] if cells else {}
    print(f"\n  Sample cell keys: {list(sample_cell.keys())[:15]}")

# ============================================================
# FAILURE 3: Check 12 - Unresolved tasks
# ============================================================
print("\n" + "=" * 60)
print("FAILURE 3: Check 12 - Unresolved tasks")
print("=" * 60)
crosswalk = load_json("bank_taxonomy_crosswalk_summary.json", "crosswalk")
if crosswalk:
    unresolved = crosswalk.get("unresolved_task_ids", [])
    print(f"  Unresolved task count: {len(unresolved)}")
    if unresolved:
        print(f"  Sample unresolved: {unresolved[:10]}")

# ============================================================
# FAILURE 4: Check 16 - Stage6 entries missing required fields
# ============================================================
print("\n" + "=" * 60)
print("FAILURE 4: Check 16 - Stage6 entries missing fields")
print("=" * 60)
stage6 = load_json("stage6_contamination_audit.json", "stage6")
if stage6:
    print(f"  Stage6 top-level keys: {list(stage6.keys())}")
    # Check each section
    for section in ["valid", "invalid_topic", "combo_mismatch"]:
        entries = stage6.get(section, [])
        if entries:
            print(f"\n  Section '{section}': {len(entries)} entries")
            print(f"  First entry keys: {list(entries[0].keys())}")
            # Check what fields exist
            all_keys = set()
            for e in entries:
                all_keys.update(e.keys())
            print(f"  All field keys in section: {sorted(all_keys)}")
        else:
            print(f"\n  Section '{section}': 0 entries")

# ============================================================
# FAILURE 5: Check 22 - step14_10 tests
# ============================================================
print("\n" + "=" * 60)
print("FAILURE 5: Check 22 - step14_10 tests")
print("=" * 60)
s14_10 = load_json("step14_10_report.json", "step14_10_report")
if s14_10:
    print(f"  Top-level keys: {list(s14_10.keys())}")
    for section_key in s14_10:
        if section_key.startswith("part"):
            section = s14_10[section_key]
            print(f"\n  Section '{section_key}' keys: {list(section.keys())}")
            # Find the results/tests array
            for sub_key in section:
                val = section[sub_key]
                if isinstance(val, list) and len(val) > 0:
                    print(f"  '{sub_key}' array: {len(val)} items")
                    print(f"  First item keys: {list(val[0].keys())}")
                    print(f"  First item: {json.dumps(val[0], ensure_ascii=False)[:200]}")
                    # Check failed ones
                    failed = [v for v in val if not v.get("passed", True)]
                    print(f"  Failed count: {len(failed)}")
                    if failed:
                        print(f"  First failed: {json.dumps(failed[0], ensure_ascii=False)[:200]}")
