#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Compare pre_live vs fixed - are empty tasks in both?"""
import json

pre = json.load(open(r'../../Downloads/FORMYLA_CONDITION_COURT/runs/selection_1080_20260712_134037/curated_bank_L1_L5_pre_live.json', 'r', encoding='utf-8'))
fixed = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))

lines = []
lines.append(f'pre_live total: {len(pre)}')
lines.append(f'fixed total: {len(fixed)}')
lines.append('')

# Empty in pre_live
empty_pre = [t for t in pre if not t.get('statement')]
empty_fixed = [t for t in fixed if not t.get('statement')]
lines.append(f'Empty in pre_live: {len(empty_pre)}')
lines.append(f'Empty in fixed: {len(empty_fixed)}')
lines.append('')

# Build ID sets
def get_oids(bank):
    result = {}
    for t in bank:
        o = t.get('original_id', '')
        if o:
            try:
                oid = int(o.replace('SEL1080-', ''))
                result[oid] = t
            except: pass
    return result

pre_dict = get_oids(pre)
fixed_dict = get_oids(fixed)

pre_empty_ids = set()
for t in empty_pre:
    o = t.get('original_id','')
    if o:
        try: pre_empty_ids.add(int(o.replace('SEL1080-','')))
        except: pass

fixed_empty_ids = set()
for t in empty_fixed:
    o = t.get('original_id','')
    if o:
        try: fixed_empty_ids.add(int(o.replace('SEL1080-','')))
        except: pass

lines.append(f'pre_live empty IDs count: {len(pre_empty_ids)}')
lines.append(f'fixed empty IDs count: {len(fixed_empty_ids)}')
lines.append('')

# Check if pre_live has content for tasks that are empty in fixed
fixed_only_empty = fixed_empty_ids - pre_empty_ids
pre_only_empty = pre_empty_ids - fixed_empty_ids
both_empty = pre_empty_ids & fixed_empty_ids

lines.append(f'Empty in BOTH pre_live AND fixed: {len(both_empty)}')
lines.append(f'Empty ONLY in fixed (had content in pre_live): {len(fixed_only_empty)}')
lines.append(f'Empty ONLY in pre_live (had content in fixed): {len(pre_only_empty)}')
lines.append('')

# Show some examples of tasks that were filled in pre_live but empty in fixed
lines.append('=== Tasks that HAD content in pre_live but EMPTY in fixed (first 20) ===')
for oid in sorted(fixed_only_empty)[:20]:
    pre_t = pre_dict.get(oid, {})
    fixed_t = fixed_dict.get(oid, {})
    pre_st = (pre_t.get('statement') or '')[:80]
    lines.append(f'  SEL1080-{oid:04d}: pre_live had "{pre_st}..." -> fixed EMPTY')

lines.append('')
lines.append('=== Tasks empty in BOTH (first 20) ===')
for oid in sorted(both_empty)[:20]:
    pre_t = pre_dict.get(oid, {})
    fixed_t = fixed_dict.get(oid, {})
    pre_st = (pre_t.get('statement') or '')[:80]
    fixed_st = (fixed_t.get('statement') or '')[:80]
    lines.append(f'  SEL1080-{oid:04d}: pre_live="{pre_st}..." fixed="{fixed_st}..."')

# Also check the source JSON - maybe these are fill tasks
lines.append('')
lines.append('=== Checking fill_l3_holes_checkpoint.json ===')
try:
    fill = json.load(open('fill_l3_holes_checkpoint.json', 'r', encoding='utf-8'))
    lines.append(f'fill checkpoint keys: {list(fill.keys())[:5]}')
except: lines.append('no fill checkpoint found')

try:
    fill2 = json.load(open('fill_cell_holes_checkpoint.json', 'r', encoding='utf-8'))
    lines.append(f'cell fill checkpoint keys: {list(fill2.keys())[:5]}')
except: lines.append('no cell fill checkpoint found')

open('_diag2_output.txt', 'w', encoding='utf-8').write('\n'.join(lines))
print('DONE')
