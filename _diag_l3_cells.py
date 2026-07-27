#!/usr/bin/env python3
import json
from collections import defaultdict

# Read decisions
dec = []
with open(r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_reselection_decisions.jsonl', encoding='utf-8') as f:
    for line in f:
        dec.append(json.loads(line))

print(f'Total decisions: {len(dec)}')

# Classify by selected_ids length
empty = []
partial = []
full = []
overflow = []

for d in dec:
    g = d['cell']['grade']
    m = d['cell']['method_code']
    n = len(d.get('selected_ids', []))
    if n == 0:
        empty.append((g, m))
    elif 1 <= n <= 4:
        partial.append((g, m, n))
    elif n == 5:
        full.append((g, m))
    else:
        overflow.append((g, m, n))

print(f'\nFull (5): {len(full)}')
print(f'Partial (1-4): {len(partial)}')
print(f'Empty (0): {len(empty)}')
print(f'Overflow (>5): {len(overflow)}')
print(f'Sum: {len(full) + len(partial) + len(empty) + len(overflow)}')

deficit = sum(max(0, 5 - len(d.get('selected_ids', []))) for d in dec)
print(f'Deficit: {deficit}')

print('\n--- EMPTY cells ---')
for g, m in sorted(empty):
    print(f'  {g}-{m}')

print('\n--- PARTIAL cells ---')
for g, m, n in sorted(partial):
    print(f'  {g}-{m}: count={n}, deficit={5-n}')

print('\n--- OVERFLOW cells ---')
for g, m, n in sorted(overflow):
    print(f'  {g}-{m}: count={n}')
