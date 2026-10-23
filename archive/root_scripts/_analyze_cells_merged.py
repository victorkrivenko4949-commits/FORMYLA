#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Analyze cell-level distribution in victor49.1-5.json"""
import json, sys
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('adaptive_data/victor49.1-5.json', 'r', encoding='utf-8') as f:
    tasks = json.load(f)

print(f'Total tasks: {len(tasks)}')
print()

# Count by level
level_counts = Counter(str(t.get('level','?')).strip() for t in tasks)
print('By level:')
for lv in sorted(level_counts):
    print(f'  L{lv}: {level_counts[lv]}')
print()

# Group by cell (grade + level + subject + subtopic)
tasks_by_cell = defaultdict(list)
for t in tasks:
    grade = str(t.get('grade', '?')).strip()
    level = str(t.get('level', '?')).strip()
    subject = str(t.get('subject', '') or t.get('topic', '') or '?').strip()
    subtopic = str(t.get('subtopic', '') or '?').strip()
    cell_key = f'G{grade}_L{level}_{subject}_{subtopic}'
    tasks_by_cell[cell_key].append(t)

print(f'Total unique cells: {len(tasks_by_cell)}')
print()

# Distribution of tasks per cell
cell_sizes = Counter(len(v) for v in tasks_by_cell.values())
print('Cell size distribution:')
for size in sorted(cell_sizes):
    print(f'  {size} tasks: {cell_sizes[size]} cells')
print()

# Over/under filled
overfilled = {k: v for k, v in tasks_by_cell.items() if len(v) > 5}
underfilled = {k: v for k, v in tasks_by_cell.items() if len(v) < 5}
exact = {k: v for k, v in tasks_by_cell.items() if len(v) == 5}

print(f'Overfilled cells (>5): {len(overfilled)}')
print(f'Underfilled cells (<5): {len(underfilled)}')
print(f'Exactly 5: {len(exact)}')
print()

# By level breakdown
by_level = defaultdict(lambda: {'over': 0, 'under': 0, 'exact': 0, 'count': 0, 'total_tasks': 0})
for k, v in tasks_by_cell.items():
    parts = k.split('_')
    level = parts[1][1:]  # L1 -> 1
    by_level[level]['count'] += 1
    by_level[level]['total_tasks'] += len(v)
    if len(v) > 5:
        by_level[level]['over'] += 1
    elif len(v) < 5:
        by_level[level]['under'] += 1
    else:
        by_level[level]['exact'] += 1

print('By level breakdown:')
for lv in sorted(by_level):
    b = by_level[lv]
    print(f'  L{lv}: {b["count"]} cells, {b["total_tasks"]} tasks, '
          f'{b["over"]} over, {b["under"]} under, {b["exact"]} exact')
print()

# Show worst overfilled cells
if overfilled:
    print(f'Worst overfilled cells (all {len(overfilled)}):')
    sorted_over = sorted(overfilled.items(), key=lambda x: -len(x[1]))
    for k, v in sorted_over:
        print(f'  {k}: {len(v)} tasks')
print()

# Underfilled details
if underfilled:
    print('Underfilled cells by level:')
    for lv in ['1','2','3','4','5']:
        cells = {k:v for k,v in underfilled.items() if f'_L{lv}_' in k}
        if cells:
            sizes = [len(v) for v in cells.values()]
            avg = sum(sizes)/len(sizes) if sizes else 0
            print(f'  L{lv}: {len(cells)} underfilled cells, avg size: {avg:.1f}, '
                  f'sizes: {dict(sorted(Counter(sizes).items()))}')
print()
print('DONE')
