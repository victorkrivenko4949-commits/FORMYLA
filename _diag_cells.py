#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Diagnostic: count tasks per (grade, level) cell in L1-L3."""
import json, collections

bank = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))
cells = collections.defaultdict(list)
for t in bank:
    level = t.get('level')
    grade = t.get('grade')
    target = t.get('target_level', '')
    if target in ('L1', 'L2', 'L3') and level in (1, 2, 3) and grade is not None:
        key = 'G%d|L%d' % (grade, level)
        cells[key].append(t['original_id'])

with open('_diag_cells.txt', 'w', encoding='utf-8') as f:
    f.write('=== Over-filled cells (>5) in L1-L3 ===\n')
    over = {k: v for k, v in sorted(cells.items()) if len(v) > 5}
    f.write('Total over-filled: %d\n' % len(over))
    for k, v in over.items():
        f.write('  %s: %d tasks\n' % (k, len(v)))

    f.write('\n=== Under-filled cells (<5) in L1-L3 ===\n')
    under = {k: v for k, v in sorted(cells.items()) if len(v) < 5}
    f.write('Total under-filled: %d\n' % len(under))
    for k, v in under.items():
        f.write('  %s: %d tasks\n' % (k, len(v)))

    f.write('\n=== Perfect cells (==5) in L1-L3 ===\n')
    perfect = {k: v for k, v in sorted(cells.items()) if len(v) == 5}
    f.write('Total perfect: %d\n' % len(perfect))

    f.write('\n=== All cells ===\n')
    for k, v in sorted(cells.items()):
        marker = ' OVER' if len(v) > 5 else (' UNDER' if len(v) < 5 else '')
        f.write('  %s: %d tasks%s\n' % (k, len(v), marker))

print('Written _diag_cells.txt')
