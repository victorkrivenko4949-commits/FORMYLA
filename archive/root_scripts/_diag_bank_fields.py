#!/usr/bin/env python3
"""Diagnose bank field names and the missing grade issue."""
import sys
import json
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

with open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8') as f:
    bank = json.load(f)

records = bank if isinstance(bank, list) else []
print(f'Total records: {len(records)}')

# Check field presence
field_counts = Counter()
for r in records:
    if isinstance(r, dict):
        for k in r.keys():
            field_counts[k] += 1

print('\nField presence (out of {} records):'.format(len(records)))
for k, v in sorted(field_counts.items(), key=lambda x: -x[1]):
    print(f'  {k}: {v}')

# Records without grade
no_grade = [r for r in records if isinstance(r, dict) and r.get('grade') is None]
print(f'\nRecords without grade: {len(no_grade)}')
if no_grade:
    r = no_grade[0]
    print(f'First no-grade record keys: {list(r.keys())}')
    for key in sorted(r.keys()):
        print(f'  {key}: {r.get(key)!r}')

# Check if class_level exists
has_class_level = [r for r in records if isinstance(r, dict) and r.get('class_level') is not None]
print(f'\nRecords with class_level: {len(has_class_level)}')
if has_class_level:
    r = has_class_level[0]
    print(f'  class_level={r["class_level"]!r} type={type(r["class_level"]).__name__}')
    print(f'  grade={r.get("grade")!r}')
    
# Check target_level vs level
has_target_level = [r for r in records if isinstance(r, dict) and r.get('target_level') is not None]
print(f'\nRecords with target_level: {len(has_target_level)}')
if has_target_level:
    r = has_target_level[0]
    print(f'  target_level={r["target_level"]!r} type={type(r["target_level"]).__name__}')
    print(f'  level={r.get("level")!r}')
