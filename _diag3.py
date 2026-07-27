#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Deep diagnosis: compare pre_live (old schema) vs fixed (new schema)."""
import json

pre = json.load(open(r'../../Downloads/FORMYLA_CONDITION_COURT/runs/selection_1080_20260712_134037/curated_bank_L1_L5_pre_live.json', 'r', encoding='utf-8'))
fixed = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))

lines = []

# --- Pre_live schema analysis ---
lines.append('=== PRE_LIVE SCHEMA ===')
lines.append(f'count: {len(pre)}')
t0 = pre[0]
lines.append(f'keys: {list(t0.keys())}')
lines.append(f'has statement: {"statement" in t0}, value={repr(t0.get("statement","MISSING"))[:60]}')
lines.append(f'has task_text: {"task_text" in t0}, value={repr(t0.get("task_text",""))[:60]}')
lines.append(f'has answer: {"answer" in t0}')
lines.append(f'has solution: {"solution" in t0}')
lines.append(f'has level: {"level" in t0}')
lines.append(f'has grade: {"grade" in t0}')

# Count tasks with task_text in pre_live
with_tt = sum(1 for t in pre if t.get('task_text'))
lines.append(f'tasks with task_text in pre_live: {with_tt}/{len(pre)}')

# --- Fixed schema analysis ---
lines.append('')
lines.append('=== FIXED SCHEMA ===')
lines.append(f'count: {len(fixed)}')
t0f = fixed[0]
lines.append(f'keys: {list(t0f.keys())}')
lines.append(f'has statement: {"statement" in t0f}')
lines.append(f'has answer: {"answer" in t0f}')
lines.append(f'has solution: {"solution" in t0f}')
lines.append(f'has level: {"level" in t0f}')
lines.append(f'has grade: {"grade" in t0f}')
lines.append(f'has task_text: {"task_text" in t0f}')

# --- Build ID map for pre_live ---
pre_by_oid = {}
for t in pre:
    o = t.get('original_id', '')
    if o: pre_by_oid[o] = t

fixed_by_oid = {}
for t in fixed:
    o = t.get('original_id', '')
    if o: fixed_by_oid[o] = t

# --- Analyze the 250 empty tasks in fixed ---
lines.append('')
lines.append('=== 250 EMPTY TASKS IN FIXED ===')
empty_fixed = [t for t in fixed if not t.get('statement')]
lines.append(f'empty count: {len(empty_fixed)}')

# Check: did these tasks have task_text in pre_live?
had_task_text = 0
had_no_task_text = 0
for t in empty_fixed:
    oid = t.get('original_id', '')
    pt = pre_by_oid.get(oid, {})
    if pt.get('task_text'):
        had_task_text += 1
    else:
        had_no_task_text += 1

lines.append(f'empty in fixed that HAD task_text in pre_live: {had_task_text}')
lines.append(f'empty in fixed that had NO task_text in pre_live: {had_no_task_text}')

# Show first 10 examples
lines.append('')
lines.append('First 10 empty-in-fixed tasks:')
for t in empty_fixed[:10]:
    oid = t.get('original_id', '')
    pt = pre_by_oid.get(oid, {})
    tt = pt.get('task_text', '')
    lines.append(f'  {oid}: pre_live.task_text={repr(tt[:80])}')

# --- Check 424 filled tasks: did they come from pre_live.task_text or from regeneration? ---
lines.append('')
lines.append('=== 424 FILLED TASKS IN FIXED ===')
filled_fixed = [t for t in fixed if t.get('statement')]
lines.append(f'filled count: {len(filled_fixed)}')

had_task_text_pre = 0
no_task_text_pre = 0
for t in filled_fixed:
    oid = t.get('original_id', '')
    pt = pre_by_oid.get(oid, {})
    if pt.get('task_text'):
        had_task_text_pre += 1
    else:
        no_task_text_pre += 1

lines.append(f'filled in fixed that HAD task_text in pre_live: {had_task_text_pre}')
lines.append(f'filled in fixed that had NO task_text in pre_live: {no_task_text_pre}')

# --- Check source field on empty tasks ---
lines.append('')
lines.append('=== SOURCE FIELD ON EMPTY TASKS ===')
srcs = {}
for t in empty_fixed:
    s = t.get('source', 'MISSING')
    srcs[s] = srcs.get(s, 0) + 1
lines.append(f'source distribution on empty tasks: {srcs}')

# --- Check changes_made on empty tasks ---
has_changes = sum(1 for t in empty_fixed if t.get('changes_made'))
lines.append(f'empty tasks with changes_made: {has_changes}')

# --- What about the pre_live tasks themselves? Did they have any data? ---
lines.append('')
lines.append('=== PRE_LIVE TASK TEXT ANALYSIS ===')
tt_lengths = [len(t.get('task_text', '')) for t in pre]
lines.append(f'task_text length: min={min(tt_lengths)}, max={max(tt_lengths)}, avg={sum(tt_lengths)/len(tt_lengths):.0f}')
empty_tt = sum(1 for l in tt_lengths if l == 0)
lines.append(f'tasks with empty task_text in pre_live: {empty_tt}')

# --- Check original source of the 250 empty tasks ---
lines.append('')
lines.append('=== TOPIC DISTRIBUTION OF EMPTY TASKS (in fixed) ===')
topics = {}
for t in empty_fixed:
    top = t.get('topic', '?')
    topics[top] = topics.get(top, 0) + 1
for top, cnt in sorted(topics.items(), key=lambda x: -x[1]):
    lines.append(f'  {top}: {cnt}')

# --- Check if empty tasks come from regeneration process ---
lines.append('')
lines.append('=== AUDIT/REGENERATION STATUS ===')
# Check if any audit results reference these tasks
try:
    audit = json.load(open('audit_675_full_results.json', 'r', encoding='utf-8'))
    empty_oids = set()
    for t in empty_fixed:
        o = t.get('original_id', '')
        if o: empty_oids.add(o)
    
    in_audit = 0
    for task_id_str, result in audit.items():
        if result.get('original_id', '') in empty_oids:
            in_audit += 1
    lines.append(f'empty tasks found in audit_675_full_results: {in_audit}')
except Exception as e:
    lines.append(f'audit check error: {e}')

open('_diag3_output.txt', 'w', encoding='utf-8').write('\n'.join(lines))
print('DONE')
