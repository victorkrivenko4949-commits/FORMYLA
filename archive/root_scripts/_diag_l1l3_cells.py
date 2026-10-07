#!/usr/bin/env python3
"""Diagnostic: count L1-L3 cells using grade/level fields (correct approach)."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
from collections import Counter, defaultdict

bank = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))

# Use grade and level fields (not class_level/target_level)
l1l3 = [t for t in bank if str(t.get('level','')) in ('1','2','3')]
l4l5 = [t for t in bank if str(t.get('level','')) in ('4','5')]
unknown = [t for t in bank if str(t.get('level','')) not in ('1','2','3','4','5')]

print('=== L1-L3 CELL COUNT via grade/level fields ===')
print(f'Total bank records: {len(bank)}')
print(f'L1-L3 (level=1/2/3): {len(l1l3)}')
print(f'L4-L5 (level=4/5): {len(l4l5)}')
print(f'Unknown level: {len(unknown)}')

# === Grade|Level cells (same as canonical taxonomy grouping) ===
gl = Counter()
for t in l1l3:
    g = str(t.get('grade','?'))
    l = 'L' + str(t.get('level','?'))
    gl[f'G{g}|{l}'] += 1

print(f'\n=== Grade|Level cells: {len(gl)} total ===')
perfect = under = over = 0
for k in sorted(gl):
    v = gl[k]
    tag = ''
    if v == 5: tag = ' PERFECT'; perfect += 1
    elif v < 5: tag = f' underfilled({v})'; under += 1
    else: tag = f' OVERFILLED({v})'; over += 1
    print(f'  {k}: {v}{tag}')
print(f'Perfect(5): {perfect}, Underfilled(<5): {under}, Overfilled(>5): {over}')

# Per level totals
l1 = sum(1 for t in l1l3 if t.get('level')==1)
l2 = sum(1 for t in l1l3 if t.get('level')==2)
l3 = sum(1 for t in l1l3 if t.get('level')==3)
print(f'\n=== Per-level task counts ===')
print(f'L1: {l1} tasks')
print(f'L2: {l2} tasks')
print(f'L3: {l3} tasks')

# === Subtopic cells (grade|level|topic|subtopic) ===
cells = defaultdict(list)
for t in l1l3:
    g = t.get('grade','?')
    l = 'L' + str(t.get('level','?'))
    topic = t.get('topic','__NO_TOPIC__')
    subtopic = t.get('subtopic','') or '__NO_SUBTOPIC__'
    cell_key = f'G{g}|{l}|{topic}|{subtopic}'
    cells[cell_key].append(t.get('original_id','?'))

print(f'\n=== Subtopic cells: {len(cells)} total ===')
perfect_s = sum(1 for v in cells.values() if len(v)==5)
under_s = sum(1 for v in cells.values() if 0<len(v)<5)
over_s = sum(1 for v in cells.values() if len(v)>5)
print(f'Perfect(5): {perfect_s}, Underfilled(<5): {under_s}, Overfilled(>5): {over_s}')

if over_s > 0:
    print(f'\n=== Overfilled subtopic cells ({over_s}) ===')
    for k in sorted(cells):
        v = cells[k]
        if len(v) > 5:
            print(f'  {k}: {len(v)} tasks')

# === Compare with _diag_report.py approach (class_level/target_level) ===
print(f'\n=== Comparison: grade/level vs class_level/target_level ===')
ct = Counter()
for t in bank:
    g = str(t.get('class_level','?'))
    l = t.get('target_level','?')
    ct