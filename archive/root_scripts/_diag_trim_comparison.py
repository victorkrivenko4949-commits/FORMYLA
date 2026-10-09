#!/usr/bin/env python
"""Compare before-trim and after-trim banks."""
import json
from collections import Counter

before = json.load(open('backups/curated_bank_before_trim_20260717_220340.json','r',encoding='utf-8'))
after = json.load(open('curated_bank_L1_L5_fixed.json','r',encoding='utf-8'))

lines = []
lines.append(f'Before trim: {len(before)} tasks total')
lines.append(f'After trim:  {len(after)} tasks total')
lines.append(f'Removed: {len(before) - len(after)} tasks')

before_ids = set(t.get('original_id','') for t in before)
after_ids = set(t.get('original_id','') for t in after)
removed = before_ids - after_ids
lines.append(f'Removed {len(removed)} unique task IDs')

before_target = [t for t in before if t.get('target_level','') in {'L1','L2','L3'}]
after_target = [t for t in after if t.get('target_level','') in {'L1','L2','L3'}]
lines.append(f'Before L1-L3: {len(before_target)}')
lines.append(f'After L1-L3:  {len(after_target)}')
lines.append(f'Removed L1-L3: {len(before_target) - len(after_target)}')

before_levels = Counter(t.get('target_level','?') for t in before)
after_levels = Counter(t.get('target_level','?') for t in after)
lines.append(f'Before levels: {dict(before_levels)}')
lines.append(f'After levels:  {dict(after_levels)}')

# Analyze removed tasks by grade|level|subtopic
source = None
try:
    source = json.load(open(r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_completed.json','r',encoding='utf-8'))
except:
    lines.append('WARNING: Could not load source file for subtopic mapping')

# Count grade|level|subtopic cells before and after
if source:
    def get_cell_key(t):
        si = t.get('source_index')
        grade = t.get('class_level')
        level = t.get('target_level','?')
        subtopic = None
        if si is not None and 0 <= si < len(source):
            src = source[si]
            subtopic = src.get('subtopic','').strip()
        if not subtopic:
            subtopic = '__NO_SUBTOPIC__'
        return f"G{grade or '?'}|{level}|{subtopic}"
    
    before_cells = Counter()
    after_cells = Counter()
    for t in before_target:
        before_cells[get_cell_key(t)] += 1
    for t in after_target:
        after_cells[get_cell_key(t)] += 1
    
    perfect_before = sum(1 for v in before_cells.values() if v == 5)
    perfect_after = sum(1 for v in after_cells.values() if v == 5)
    under_before = sum(1 for v in before_cells.values() if 1 <= v < 5)
    under_after = sum(1 for v in after_cells.values() if 1 <= v < 5)
    over_before = sum(1 for v in before_cells.values() if v > 5)
    over_after = sum(1 for v in after_cells.values() if v > 5)
    
    lines.append(f'')
    lines.append(f'=== GRADE|LEVEL|SUBTOPIC CELLS ===')
    lines.append(f'Before: {len(before_cells)} cells ({perfect_before} perfect, {under_before} underfilled, {over_before} overfilled)')
    lines.append(f'After:  {len(after_cells)} cells ({perfect_after} perfect, {under_after} underfilled, {over_after} overfilled)')
    
    # Find cells that changed
    all_keys = set(before_cells.keys()) | set(after_cells.keys())
    changed = []
    for k in sorted(all_keys):
        b = before_cells.get(k, 0)
        a = after_cells.get(k, 0)
        if b != a:
            changed.append((k, b, a))
    
    lines.append(f'')
    lines.append(f'Cells that lost tasks (before -> after):')
    for k, b, a in changed:
        if a < b:
            lines.append(f'  {k}: {b} -> {a} (lost {b-a})')

with open('_diag_trim_comparison.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print('\n'.join(lines))
