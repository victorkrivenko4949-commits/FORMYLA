#!/usr/bin/env python
"""Diagnostic: get accurate counts for FINAL_REPORT.md update."""
import json
from collections import Counter, defaultdict

bank = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))
source = json.load(open(r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_completed.json', 'r', encoding='utf-8'))

total = len(bank)
l1l3 = [t for t in bank if t.get('target_level', '') in {'L1', 'L2', 'L3'}]
l4l5 = [t for t in bank if t.get('target_level', '') in {'L4', 'L5'}]
print(f'Total: {total}')
print(f'L1-L3: {len(l1l3)}')
print(f'L4-L5: {len(l4l5)}')

# Matrix grades
matrix_grades = {'2', '5', '6', '7', '8', '9', '10', '11'}
matrix = [t for t in l1l3 if str(t.get('class_level', '')) in matrix_grades]
other = [t for t in l1l3 if str(t.get('class_level', '')) not in matrix_grades]
print(f'L1-L3 in matrix (G2, G5-11): {len(matrix)}')
print(f'L1-L3 outside matrix: {len(other)}')

# Grade|Level counts
gl = Counter()
for t in l1l3:
    g = str(t.get('class_level', '?'))
    l = t.get('target_level', '?')
    gl[f'G{g}|{l}'] += 1

print()
print('=== Grade|Level counts (all L1-L3) ===')
perfect = 0
under = 0
over = 0
missing = 0
for k in sorted(gl):
    v = gl[k]
    tag = ''
    if v == 5: tag = ' PERFECT'; perfect += 1
    elif v < 5: tag = f' underfilled({v})'; under += 1
    else: tag = f' OVERFILLED({v})'; over += 1
    print(f'  {k}: {v}{tag}')

# Check for missing cells in matrix
all_grades = sorted(matrix_grades)
all_levels = ['L1', 'L2', 'L3']
print()
print('=== Matrix cells (G2,G5-11 x L1,L2,L3) ===')
matrix_total = 0
for g in all_grades:
    row = []
    for l in all_levels:
        key = f'G{g}|{l}'
        v = gl.get(key, 0)
        row.append(v)
        matrix_total += v
    print(f'  G{g}: L1={row[0]}, L2={row[1]}, L3={row[2]}')
print(f'Matrix total tasks: {matrix_total}')

# Subtopic cells
target = l1l3
cells = defaultdict(list)
for t in target:
    si = t.get('source_index')
    grade = t.get('class_level')
    level = t.get('target_level', '?')
    subtopic = None
    if si is not None and 0 <= si < len(source):
        src = source[si]
        if grade is None and src.get('grade') is not None:
            grade = src['grade']
        subtopic = src.get('subtopic', '').strip()
    if not subtopic:
        subtopic = '__NO_SUBTOPIC__'
    cell_key = f"G{grade or '?'}|{level}|{subtopic}"
    cells[cell_key].append(t.get('original_id', '?'))

print()
print(f'=== Subtopic cells: {len(cells)} total ===')
perfect_s = sum(1 for v in cells.values() if len(v) == 5)
under_s = sum(1 for v in cells.values() if 0 < len(v) < 5)
over_s = sum(1 for v in cells.values() if len(v) > 5)
print(f'Perfect: {perfect_s}, Underfilled: {under_s}, Overfilled: {over_s}')

# Show overfilled cells
print()
print('=== Overfilled subtopic cells (before trim) ===')
for k in sorted(cells):
    v = cells[k]
    if len(v) > 5:
        print(f'  {k}: {len(v)} tasks')

# Now get per-grade|level breakdown for the matrix
print()
print('=== L1-L3 per level totals ===')
l1_count = sum(1 for t in l1l3 if t.get('target_level') == 'L1')
l2_count = sum(1 for t in l1l3 if t.get('target_level') == 'L2')
l3_count = sum(1 for t in l1l3 if t.get('target_level') == 'L3')
print(f'L1: {l1_count}, L2: {l2_count}, L3: {l3_count}')
