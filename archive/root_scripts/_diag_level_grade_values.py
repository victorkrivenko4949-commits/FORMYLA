#!/usr/bin/env python3
"""Check what level/grade values actually exist in the bank."""
import json
from collections import Counter

bank = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))

level_vals = Counter()
grade_vals = Counter()
for t in bank:
    level_vals[str(t.get('level'))] += 1
    grade_vals[str(t.get('grade'))] += 1

print('=== Level values ===')
for k, v in sorted(level_vals.items(), key=lambda x: (x[0] if x[0] != 'None' else 'zzz')):
    print(f'  level={k}: {v}')

print('\n=== Grade values ===')
for k, v in sorted(grade_vals.items(), key=lambda x: (x[0] if x[0] != 'None' else 'zzz')):
    print(f'  grade={k}: {v}')

print('\n=== Sample unknown level tasks (first 10) ===')
count = 0
for t in bank:
    lv = t.get('level')
    if str(lv) not in ('1', '2', '3', '4', '5'):
        print(f'  original_id={t.get("original_id","?")}, level={lv!r}, grade={t.get("grade")}, '
              f'class_level={t.get("class_level")}, target_level={t.get("target_level")}')
        count += 1
        if count >= 10:
            break

print('\n=== Tasks with grade=None/unknown ===')
gcount = 0
for t in bank:
    gv = t.get('grade')
    if gv is None or str(gv) == 'None' or gv == '?':
        lv = t.get('level')
        print(f'  original_id={t.get("original_id","?")}, grade={gv!r}, level={lv!r}, '
              f'class_level={t.get("class_level")}, target_level={t.get("target_level")}')
        gcount += 1
        if gcount >= 10:
            break
