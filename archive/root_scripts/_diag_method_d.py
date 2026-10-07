#!/usr/bin/env python3
"""Diagnose Method D: check why metadata join fails."""
import sys
import json

# Force utf-8
sys.stdout.reconfigure(encoding='utf-8')

# Load canonical dict
with open('l4_l5_finalization/taxonomy_reconstruction/canonical_taxonomy.json', 'r', encoding='utf-8') as f:
    canon = json.load(f)

canonical_dict = {}
for cc in canon.get('canonical_cells', []):
    canonical_dict[cc['cell_key']] = {
        'grade': cc['grade'],
        'level': cc['level'],
        'topic_id': cc['topic_id'],
        'theme_name': cc['theme_name'],
        'subtopic_index': cc['subtopic_index'],
        'subtopic_name': cc['subtopic_name']
    }

# Build grade+level+topic lookup
from collections import defaultdict
grade_level_topic_lookup = defaultdict(list)
for ck, cinfo in canonical_dict.items():
    meta_key = (cinfo['grade'], cinfo['level'], cinfo['theme_name'])
    grade_level_topic_lookup[meta_key].append(ck)

print(f'Lookup has {len(grade_level_topic_lookup)} unique keys')

# Check some keys that might match the first bank record (grade=5, level=L1, topic='Числа и делимость')
print('\n=== Checking for grade=5, level=L1, theme=Числа и делимость ===')
key = (5, 'L1', 'Числа и делимость')
print(f'  Key: ({5!r}, {"L1"!r}, {"Числа и делимость"!r})')
if key in grade_level_topic_lookup:
    print(f'  FOUND! cells: {grade_level_topic_lookup[key]}')
else:
    print(f'  NOT FOUND')
    # Show what keys exist for grade 5
    g5_keys = [(k, v) for k, v in grade_level_topic_lookup.items() if k[0] == 5]
    print(f'\n  All grade 5 keys ({len(g5_keys)}):')
    for mk, cells in g5_keys[:20]:
        print(f'    ({mk[0]!r}, {mk[1]!r}, {mk[2]!r}) -> {cells[:2]}')

# Now check the first bank record
print('\n=== First bank record fields ===')
with open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8') as f:
    bank = json.load(f)

if isinstance(bank, list):
    records = bank
else:
    records = bank.get('tasks', bank.get('records', bank.get('items', [])))

if records:
    r = records[0]
    print(f'  grade: {r.get("grade")!r} (type: {type(r.get("grade")).__name__})')
    print(f'  level: {r.get("level")!r} (type: {type(r.get("level")).__name__})')
    print(f'  topic: {r.get("topic")!r} (type: {type(r.get("topic")).__name__})')
    print(f'  theme_name: {r.get("theme_name")!r}')
    print(f'  original_id: {r.get("original_id")!r}')
    
    # Build the key the same way as the code does
    bank_grade = r.get('grade')
    bank_level = r.get('level')
    bank_topic = r.get('topic') or r.get('theme_name') or ''
    print(f'\n  Method D would build:')
    print(f'    bank_grade={bank_grade!r}')
    print(f'    level_key=f"L{bank_level}" = {"L" + str(bank_level)!r}')
    print(f'    meta_key = ({int(bank_grade)!r}, {"L" + str(bank_level)!r}, {bank_topic!r})')
    
    meta_key_d = (int(bank_grade), f"L{bank_level}", bank_topic)
    print(f'    = ({meta_key_d[0]!r}, {meta_key_d[1]!r}, {meta_key_d[2]!r})')
    
    if meta_key_d in grade_level_topic_lookup:
        print(f'  >>> MATCH FOUND! cells: {grade_level_topic_lookup[meta_key_d]}')
    else:
        print(f'  >>> NO MATCH')
        
        # Show closest keys
        print(f'\n  Closest grade 5 keys:')
        for mk, cells in sorted(grade_level_topic_lookup.items()):
            if mk[0] == 5 and 'L1' in mk[1]:
                print(f'    {mk} -> {cells}')
    