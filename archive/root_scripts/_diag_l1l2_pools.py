#!/usr/bin/env python3
"""Diagnostic: analyze L1/L2 candidate pool sizes for DeepSeek reselection."""
import json
from collections import defaultdict, Counter

MAIN_PATH = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels.json'
RESERVE_PATH = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_reserve.json'

with open(MAIN_PATH, 'r', encoding='utf-8') as f:
    main = json.load(f)
with open(RESERVE_PATH, 'r', encoding='utf-8') as f:
    reserve = json.load(f)

print(f"MAIN: {len(main)} tasks")
print(f"RESERVE: {len(reserve)} tasks")
if main:
    print(f"Main keys: {list(main[0].keys())}")
if reserve:
    print(f"Reserve keys: {list(reserve[0].keys())}")

# L1/L2 cells in main
cells_m = defaultdict(int)
for t in main:
    d = t.get('difficulty')
    if d in (1, 2):
        cells_m[(t['grade'], t['method_code'], d)] += 1

# L1/L2 cells in reserve
cells_r = defaultdict(int)
for t in reserve:
    d = t.get('difficulty')
    if d in (1, 2):
        cells_r[(t['grade'], t['method_code'], d)] += 1

l1_main = {k: v for k, v in cells_m.items() if k[2] == 1}
l2_main = {k: v for k, v in cells_m.items() if k[2] == 2}
l1_res = {k: v for k, v in cells_r.items() if k[2] == 1}
l2_res = {k: v for k, v in cells_r.items() if k[2] == 2}

print(f"\nL1 cells in main: {len(l1_main)}, tasks: {sum(l1_main.values())}")
print(f"L2 cells in main: {len(l2_main)}, tasks: {sum(l2_main.values())}")
print(f"L1 cells in reserve: {len(l1_res)}, tasks: {sum(l1_res.values())}")
print(f"L2 cells in reserve: {len(l2_res)}, tasks: {sum(l2_res.values())}")

# Pool per cell
all_cells = defaultdict(lambda: [0, 0])
for t in main:
    d = t.get('difficulty')
    if d in (1, 2):
        all_cells[(t['grade'], t['method_code'], d)][0] += 1
for t in reserve:
    d = t.get('difficulty')
    if d in (1, 2):
        all_cells[(t['grade'], t['method_code'], d)][1] += 1

pool_l1 = Counter()
pool_l2 = Counter()
for k, v in all_cells.items():
    total = v[0] + v[1]
    if k[2] == 1:
        pool_l1[total] += 1
    else:
        pool_l2[total] += 1

print(f"\nL1 pool size distribution (main + reserve per cell):")
for sz in sorted(pool_l1.keys()):
    print(f"  {sz} candidates: {pool_l1[sz]} cells")

print(f"\nL2 pool size distribution (main + reserve per cell):")
for sz in sorted(pool_l2.keys()):
    print(f"  {sz} candidates: {pool_l2[sz]} cells")

# Combined
pool_all = Counter()
for k, v in all_cells.items():
    total = v[0] + v[1]
    pool_all[total] += 1
print(f"\nCombined L1+L2 pool:")
print(f"  Cells with <=5 candidates (no API call): {sum(v for k,v in pool_all.items() if k <= 5)}")
print(f"  Cells with 6-15 candidates (1 API call each): {sum(v for k,v in pool_all.items() if 6 <= k <= 15)}")
print(f"  Cells with >15 candidates (pre-filter + API call): {sum(v for k,v in pool_all.items() if k > 15)}")

print(f"\nTotal L1+L2 cells: {len(all_cells)}")
print(f"Total API calls needed (L1+L2): ", end="")
api_calls = sum(v for k,v in pool_all.items() if k > 5)
print(api_calls)
