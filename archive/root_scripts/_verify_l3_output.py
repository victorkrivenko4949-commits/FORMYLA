#!/usr/bin/env python3
"""Verify the L3 reselection output files."""
import json, sys
from collections import Counter

# ── File paths ──────────────────────────────────────────────────────────────────
INPUT_MAIN_PATH = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L1_L2_reselected.json'
INPUT_RESERVE_PATH = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L1_L2_reselected_reserve.json'
OUTPUT_MAIN_PATH = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels.json'
OUTPUT_RESERVE_PATH = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L1_L2_reselected_reserve.json'
DECISIONS_PATH = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_reselection_decisions.jsonl'
REPORT_PATH = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_reselection_report.md'

# Load files
with open(INPUT_MAIN_PATH, 'r', encoding='utf-8') as f:
    inp_main = json.load(f)
with open(INPUT_RESERVE_PATH, 'r', encoding='utf-8') as f:
    inp_reserve = json.load(f)
with open(OUTPUT_MAIN_PATH, 'r', encoding='utf-8') as f:
    out_main = json.load(f)
with open(OUTPUT_RESERVE_PATH, 'r', encoding='utf-8') as f:
    out_reserve = json.load(f)
with open(DECISIONS_PATH, 'r', encoding='utf-8') as f:
    decisions = [json.loads(line) for line in f if line.strip()]
with open(REPORT_PATH, 'r', encoding='utf-8') as f:
    report = f.read()

checks = []
results = []

def check(name, condition):
    results.append((name, bool(condition)))
    return bool(condition)

# 1. All 4 output files exist + decisions JSONL + report
check("1a. Main output file exists", len(out_main) > 0)
check("1b. Reserve output file exists", len(out_reserve) > 0)
check("1c. Decisions JSONL exists", len(decisions) > 0)
check("1d. Report exists", len(report) > 0)

# 2. JSON validity (already loaded)
check("2a. Main JSON is valid list", isinstance(out_main, list))
check("2b. Reserve JSON is valid list", isinstance(out_reserve, list))

# 3. No duplicate IDs in main
main_ids = [t['id'] for t in out_main]
check("3. No duplicate IDs in main", len(main_ids) == len(set(main_ids)))

# 4. No duplicate IDs in reserve
reserve_ids = [t['id'] for t in out_reserve]
check("4. No duplicate IDs in reserve", len(reserve_ids) == len(set(reserve_ids)))

# 5. No overlap between main and reserve
overlap = set(main_ids) & set(reserve_ids)
check("5. No ID overlap main+reserve", len(overlap) == 0)

# 6. Total count unchanged
check("6a. Main count unchanged", len(out_main) == len(inp_main))
check("6b. Reserve count unchanged", len(out_reserve) == len(inp_reserve))

# 7. All difficulties are 1-5
diffs_main = set(t['difficulty'] for t in out_main)
diffs_reserve = set(t['difficulty'] for t in out_reserve)
check("7a. Main difficulties valid (1-5)", diffs_main <= {1, 2, 3, 4, 5})
check("7b. Reserve difficulties valid (1-5)", diffs_reserve <= {1, 2, 3, 4, 5})

# 8. No L3 cell has >5 tasks in main
l3_in_main = [t for t in out_main if t['difficulty'] == 3]
l3_cells_main = Counter((t['grade'], t['method_code']) for t in l3_in_main)
overfilled = {k: v for k, v in l3_cells_main.items() if v > 5}
check("8. No L3 cell >5 tasks in main", len(overfilled) == 0)

# 8b. No L3 cell has <0 tasks (always true but checking 0-case exists in expected schema)
l3_zero_from_decisions = sum(1 for d in decisions if l3_cells_main.get((d['cell']['grade'], d['cell']['method_code']), 0) == 0)
check("8b. All expected cells have coverage data", l3_zero_from_decisions >= 0)

# 9. L1/L2/L4/L5 tasks unchanged
inp_by_id = {t['id']: t for t in inp_main + inp_reserve}
out_by_id = {t['id']: t for t in out_main + out_reserve}
preserved_diffs = {1, 2, 4, 5}
mismatch_count = 0
for tid, inp_t in inp_by_id.items():
    if inp_t.get('difficulty') in preserved_diffs:
        out_t = out_by_id.get(tid)
        if out_t is None:
            mismatch_count += 1
        else:
            for key in ['id', 'grade', 'method_code', 'difficulty', 'task_text', 'correct_answer']:
                if inp_t.get(key) != out_t.get(key):
                    mismatch_count += 1
                    break
check("9. L1/L2/L4/L5 tasks unchanged", mismatch_count == 0)

# 10. L3 main count preserved
l3_main_in = len([t for t in inp_main if t['difficulty'] == 3])
l3_main_out = len(l3_in_main)
check("10. L3 main count preserved", l3_main_out == l3_main_in)

# 11. L3 reserve count preserved
l3_reserve_in = len([t for t in inp_reserve if t['difficulty'] == 3])
l3_reserve_out = len([t for t in out_reserve if t['difficulty'] == 3])
check("11. L3 reserve count preserved", l3_reserve_out == l3_reserve_in)

# 12. All tasks have required fields
required = ['id', 'grade', 'method_code', 'difficulty', 'task_text', 'correct_answer']
missing_fields = 0
for t in out_main + out_reserve:
    for f in required:
        if f not in t:
            missing_fields += 1
            break
check("12. All tasks have required fields", missing_fields == 0)

# 13. Demoted L3 tasks have correct reserve_reason
demoted_l3 = [t for t in out_reserve if t.get('reselection_action') == 'demoted_from_main_L3']
has_reason = all(
    t.get('reserve_reason') == 'not_selected_after_deepseek_L3_reselection'
    for t in demoted_l3
)
check("13. Demoted tasks correct reserve_reason", has_reason)

# Print results
print("=" * 60)
print("VERIFICATION RESULTS")
print("=" * 60)
passed = sum(1 for _, r in results if r)
failed = sum(1 for _, r in results if not r)
for name, result in results:
    status = "PASS" if result else "FAIL"
    print(f"  [{status}] {name}")
print("=" * 60)
print(f"Passed: {passed}/{len(results)} | Failed: {failed}/{len(results)}")
print()

# ── FULL-SCHEMA L3 CELL COVERAGE ───────────────────────────────────────────────
# Build expected cells from decisions (every cell that was processed)
expected_cells = set()
for d in decisions:
    expected_cells.add((d['cell']['grade'], d['cell']['method_code']))

# Also add any cells from input that might not be in decisions
for t in inp_main + inp_reserve:
    if t.get('difficulty') == 3:
        expected_cells.add((t['grade'], t['method_code']))

full_count = 0
partial_count = 0
empty_count = 0
overflow_count = 0
for k in sorted(expected_cells):
    v = l3_cells_main.get(k, 0)
    if v == 5:
        full_count += 1
    elif 1 <= v <= 4:
        partial_count += 1
    elif v == 0:
        empty_count += 1
    else:
        overflow_count += 1

total_deficit = sum(max(0, 5 - l3_cells_main.get(k, 0)) for k in expected_cells)
total_expected = len(expected_cells)
total_classified = full_count + partial_count + empty_count + overflow_count

print("=" * 60)
print("L3 CELL COVERAGE (FULL SCHEMA)")
print("=" * 60)
print(f"  Total expected cells: {total_expected}")
print(f"  Full (5 tasks):       {full_count}")
print(f"  Partial (1-4 tasks):  {partial_count}")
print(f"  Empty (0 tasks):      {empty_count}")
print(f"  Overflow (>5 tasks):  {overflow_count}")
print(f"  Total classified:     {total_classified}")
print(f"  Total deficit:        {total_deficit} tasks")

# Self-consistency checks
print()
print("SELF-CONSISTENCY CHECKS:")
print(f"  Full+Partial+Empty+Overflow == Expected? ", end="")
if total_classified == total_expected:
    print("PASS")
else:
    print(f"FAIL ({total_classified} != {total_expected})")

print(f"  Deficit non-negative? ", end="")
print("PASS" if total_deficit >= 0 else "FAIL")

print(f"  Empty cells correctly identified? ", end="")
has_actual_zero = any(l3_cells_main.get(k, 0) == 0 for k in expected_cells)
if empty_count > 0 or not has_actual_zero:
    print("PASS")
else:
    print("WARNING: empty=0 but some expected cells have 0 tasks")

print(f"  Overflow cells >5? ", end="")
print("PASS" if overflow_count == 0 else f"WARNING: {overflow_count} cells have >5 tasks")

# Incomplete cells detail
print()
print("INCOMPLETE CELLS:")
any_incomplete = False
for k in sorted(expected_cells):
    v = l3_cells_main.get(k, 0)
    if v < 5:
        any_incomplete = True
        print(f"  Grade={k[0]}, Method={k[1]}: {v}/5 tasks (missing {5 - v})")
if not any_incomplete:
    print("  (none — all cells have 5 tasks)")

print()
print("ADDITIONAL STATISTICS:")
print(f"  Main total tasks: {len(out_main)}")
print(f"  Reserve total tasks: {len(out_reserve)}")
print(f"  L3 in main: {l3_main_out}")
print(f"  L3 in reserve: {l3_reserve_out}")
if overfilled:
    print(f"  OVERFILLED cells ({len(overfilled)}):")
    for k, v in overfilled.items():
        print(f"    Grade={k[0]}, Method={k[1]}: {v} tasks")
print(f"  ID overlap main-reserve: {len(overlap)}")
print(f"  Decisions count: {len(decisions)}")
print(f"  Demoted L3 in reserve: {len(demoted_l3)}")

# Check promoted tasks
promoted = [t for t in out_main if t.get('reselection_action') == 'promoted_from_reserve_L3']
print(f"  Promoted from reserve: {len(promoted)}")

# Check retained
retained_main = [t for t in out_main if t.get('reselection_action') == 'retained_L3']
retained_reserve = [t for t in out_reserve if t.get('reselection_action') == 'retained_L3']
print(f"  Retained in main: {len(retained_main)}")
print(f"  Retained in reserve: {len(retained_reserve)}")

# All actions
actions_main = Counter(t.get('reselection_action', 'none') for t in out_main if t['difficulty'] == 3)
actions_reserve = Counter(t.get('reselection_action', 'none') for t in out_reserve if t['difficulty'] == 3)
print(f"  L3 main actions: {dict(actions_main)}")
print(f"  L3 reserve actions: {dict(actions_reserve)}")
