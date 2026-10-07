#!/usr/bin/env python
"""Detailed analysis of trim impact on grade|level|subtopic cells."""
import json
from collections import Counter

before = json.load(open('backups/curated_bank_before_trim_20260717_220340.json','r',encoding='utf-8'))
after = json.load(open('curated_bank_L1_L5_fixed.json','r',encoding='utf-8'))
source = json.load(open(r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_completed.json','r',encoding='utf-8'))

def get_cell_key(t):
    si = t.get('source_index')
    grade = t.get('class_level')
    level = t.get('target_level','?')
    subtopic = None
    if si is not None and 0 <= si < len(source):
        src = source[si]
        if grade is None and src.get('grade') is not None:
            grade = src['grade']
        subtopic = src.get('subtopic','').strip()
    if not subtopic:
        subtopic = '__NO_SUBTOPIC__'
    return f"G{grade or '?'}|{level}|{subtopic}"

before_target = [t for t in before if t.get('target_level','') in {'L1','L2','L3'}]
after_target = [t for t in after if t.get('target_level','') in {'L1','L2','L3'}]

before_cells = Counter()
after_cells = Counter()
for t in before_target:
    before_cells[get_cell_key(t)] += 1
for t in after_target:
    after_cells[get_cell_key(t)] += 1

all_keys = set(before_cells.keys()) | set(after_cells.keys())

print("=== CELLS THAT WERE OVERFILLED BEFORE AND WHAT THEY BECAME ===")
for k in sorted(all_keys):
    b = before_cells.get(k, 0)
    a = after_cells.get(k, 0)
    if b > 5:
        status = "PERFECT" if a == 5 else (f"UNDER({a})" if a < 5 else f"STILL_OVER({a})")
        print(f"  {k}")
        print(f"    Before={b} -> After={a} => {status}")

print()
print("=== CELLS THAT WERE PERFECT(5) BEFORE AND WHAT THEY BECAME ===")
for k in sorted(all_keys):
    b = before_cells.get(k, 0)
    a = after_cells.get(k, 0)
    if b == 5:
        status = "KEPT" if a == 5 else f"REDUCED_TO_{a}"
        print(f"  {k}")
        print(f"    Before={b} -> After={a} => {status}")

print()
print("=== CELLS THAT WERE UNDERFILLED BEFORE AND WHAT THEY BECAME ===")
for k in sorted(all_keys):
    b = before_cells.get(k, 0)
    a = after_cells.get(k, 0)
    if 1 <= b < 5:
        status = "KEPT" if a > 0 else "DESTROYED"
        print(f"  {k}")
        print(f"    Before={b} -> After={a} => {status}")

print()
print("=== SUMMARY ===")
destroyed = sum(1 for k in all_keys if before_cells.get(k,0) > 0 and after_cells.get(k,0) == 0)
reduced_below_5 = sum(1 for k in all_keys if before_cells.get(k,0) > 5 and 0 < after_cells.get(k,0) < 5)
kept_over = sum(1 for k in all_keys if before_cells.get(k,0) > 5 and after_cells.get(k,0) > 5)
became_perfect = sum(1 for k in all_keys if before_cells.get(k,0) > 5 and after_cells.get(k,0) == 5)
print(f"Cells completely destroyed (had tasks before, 0 now): {destroyed}")
print(f"Overfilled cells reduced BELOW 5: {reduced_below_5}")
print(f"Overfilled cells trimmed TO exactly 5: {became_perfect}")
print(f"Overfilled cells still over (>5): {kept_over}")
