#!/usr/bin/env python
"""Stage 0/1: Analyze the current filled DB state and build gap map."""
import json, csv, os, hashlib

DB_PATH = 'l4_l5_fill_output/curated_bank_L4_L5_filled.json'
WORK_DIR = 'l4_l5_completion_work'

os.makedirs(WORK_DIR, exist_ok=True)

db = json.load(open(DB_PATH, 'r', encoding='utf-8'))

# Group by cell_key
cells = {}
for t in db:
    ck = t.get('cell_key', '')
    cells.setdefault(ck, []).append(t)

print(f'Total tasks: {len(db)}')
print(f'Unique cells: {len(cells)}')

full = sum(1 for c in cells.values() if len(c) == 5)
partial = sum(1 for c in cells.values() if 0 < len(c) < 5)
empty = 258 - full - partial
print(f'Full (5/5): {full}')
print(f'Partial (1-4/5): {partial}')
print(f'Empty (0/5): {empty}')

needed = sum(max(0, 5 - len(c)) for c in cells.values())
print(f'Sum(needed) = {needed}')

l4 = sum(1 for t in db if t.get('class_level') == 'L4')
l5 = sum(1 for t in db if t.get('class_level') == 'L5')
print(f'L4 tasks: {l4}, L5 tasks: {l5}')
print(f'Target: 645 L4 + 645 L5 = 1290 total')

# Compute stable task hashes
for t in db:
    norm = (t.get('problem', '') or '').strip().lower()
    t['task_hash'] = hashlib.sha256(norm.encode('utf-8')).hexdigest()[:16]

# Build gaps_before.csv
incomplete = [(ck, tasks) for ck, tasks in cells.items() if len(tasks) < 5]
incomplete.sort(key=lambda x: len(x[1]))  # ascending by current_count

with open(os.path.join(WORK_DIR, 'gaps_before.csv'), 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['cell_key', 'current_count', 'needed', 'class_levels', 'topic'])
    for ck, tasks in incomplete:
        levels = ','.join(sorted(set(t.get('class_level','?') for t in tasks)))
        # Extract topic from cell_key: e.g. "5_Числа_Делимость_L4"
        parts = ck.split('_')
        topic = '_'.join(parts[1:-1]) if len(parts) >= 3 else ck
        writer.writerow([ck, len(tasks), 5 - len(tasks), levels, topic])

print(f'\nIncomplete cells written to gaps_before.csv ({len(incomplete)} rows)')
print(f'\nBreakdown by current_count:')
counts = {}
for ck, tasks in incomplete:
    n = len(tasks)
    counts[n] = counts.get(n, 0) + 1
for n in sorted(counts.keys()):
    print(f'  {n}/5: {counts[n]} cells, need {counts[n] * (5-n)} tasks')
    
# Also dump the complete list for debugging
with open(os.path.join(WORK_DIR, 'incomplete_cells.txt'), 'w', encoding='utf-8') as f:
    for ck, tasks in incomplete:
        f.write(f'{ck}: {len(tasks)}/5\n')

print(f'\nDone. Check {WORK_DIR}/ for outputs.')
