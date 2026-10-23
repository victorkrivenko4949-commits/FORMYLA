#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Диагностика: почему 674 вместо 675, и какие 250 задач без level."""
import json
from collections import Counter

bank = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))

lines = []
lines.append(f'=== TOTAL: {len(bank)} ===')
lines.append('')

# --- 1. Empty fields ---
empty_statement = [t for t in bank if not t.get('statement')]
empty_answer = [t for t in bank if not t.get('answer')]
empty_solution = [t for t in bank if not t.get('solution')]
empty_level = [t for t in bank if t.get('level') is None]
lines.append(f'Empty statement: {len(empty_statement)}')
lines.append(f'Empty answer:   {len(empty_answer)}')
lines.append(f'Empty solution: {len(empty_solution)}')
lines.append(f'Level is None:  {len(empty_level)}')
lines.append('')

# --- 2. None-level tasks detail ---
lines.append('=== NONE-LEVEL TASKS (first 30) ===')
for t in empty_level[:30]:
    oid = t.get('original_id', '?')
    topic = t.get('topic', '?')
    grade = t.get('grade', '?')
    st = (t.get('statement') or '')[:100]
    lines.append(f'  {oid} | topic={topic} | grade={grade} | {st}')
lines.append(f'  ... ({len(empty_level)} total)')
lines.append('')

# --- 3. Which tasks survived? Find the missing one from 1..1080 ---
oids = []
for t in bank:
    o = t.get('original_id', '')
    if o:
        try:
            oids.append(int(o.replace('SEL1080-', '')))
        except:
            pass
survived = set(oids)
all_ids = set(range(1, 1081))
missing = sorted(all_ids - survived)
lines.append(f'=== MISSING IDs from 1..1080: {len(missing)} ===')
lines.append(f'Missing: {missing}')
lines.append('')

# --- 4. Check for duplicate original_ids ---
id_counts = Counter(oids)
dups = {k: v for k, v in id_counts.items() if v > 1}
lines.append(f'=== DUPLICATE original_ids: {len(dups)} ===')
for k, v in sorted(dups.items()):
    lines.append(f'  SEL1080-{k:04d} appears {v} times')
lines.append('')

# --- 5. Level distribution (clean) ---
level_vals = {}
for t in bank:
    lv = t.get('level')
    lv_str = str(lv)
    level_vals[lv_str] = level_vals.get(lv_str, 0) + 1
lines.append(f'=== LEVEL distribution ===')
for k in sorted(level_vals.keys()):
    lines.append(f'  level={k}: {level_vals[k]}')
lines.append('')

# --- 6. Source field ---
src_vals = {}
for t in bank:
    s = str(t.get('source', 'MISSING'))
    src_vals[s] = src_vals.get(s, 0) + 1
lines.append(f'=== SOURCE distribution ===')
for k, v in sorted(src_vals.items(), key=lambda x: -x[1]):
    lines.append(f'  source={k}: {v}')
lines.append('')

# --- 7. None-level: do they have changes_made? ---
has_changes = sum(1 for t in empty_level if t.get('changes_made'))
lines.append(f'None-level tasks with changes_made: {has_changes}/{len(empty_level)}')
lines.append('')

# --- 8. Topic distribution of None-level tasks ---
topic_none = {}
for t in empty_level:
    top = t.get('topic', '?')
    topic_none[top] = topic_none.get(top, 0) + 1
lines.append(f'=== TOPIC distribution of None-level tasks ===')
for k, v in sorted(topic_none.items(), key=lambda x: -x[1]):
    lines.append(f'  {k}: {v}')
lines.append('')

# --- 9. Grade distribution of None-level tasks ---
grade_none = {}
for t in empty_level:
    g = t.get('grade', '?')
    grade_none[str(g)] = grade_none.get(str(g), 0) + 1
lines.append(f'=== GRADE distribution of None-level tasks ===')
for k, v in sorted(grade_none.items(), key=lambda x: -x[1]):
    lines.append(f'  grade={k}: {v}')
lines.append('')

open('_diagnose_output.txt', 'w', encoding='utf-8').write('\n'.join(lines))
print('DONE')
