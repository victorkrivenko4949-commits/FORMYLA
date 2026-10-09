#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cross-reference 250 empty fixed tasks against audit results."""
import json

fixed = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))
audit = json.load(open('audit_675_full_results.json', 'r', encoding='utf-8'))

# --- 1. Empty tasks in fixed ---
empty = [t for t in fixed if not t.get('statement')]
empty_oids = set(t.get('original_id', '') for t in empty)
print(f'Empty tasks in fixed: {len(empty)}')
print(f'Empty original_ids: {len(empty_oids)}')

# --- 2. Audit results ---
# The 'results' array contains per-task audit results
results = audit.get('results', [])
print(f'\nAudit results count: {len(results)}')

# Check structure of first result
if results:
    r0 = results[0]
    print(f'First result keys: {list(r0.keys())}')
    print(f'First result task_index: {r0.get("task_index")}')
    print(f'First result original_id: {r0.get("original_id", "N/A")}')

# Collect all task_indices that were audited
audit_indices = set()
audit_oids = set()
for r in results:
    ti = r.get('task_index')
    if ti is not None:
        audit_indices.add(ti)
    oid = r.get('original_id', r.get('task_id', ''))
    if oid:
        audit_oids.add(oid)

print(f'\nUnique task_indices in audit: {len(audit_indices)}')
print(f'Unique original_ids in audit: {len(audit_oids)}')
if audit_oids:
    print(f'Sample audit oids: {sorted(audit_oids)[:5]}')

# --- 3. Check which empty tasks have original_id in audit ---
in_audit = empty_oids & audit_oids
not_in_audit = empty_oids - audit_oids
print(f'\n=== CROSS-REFERENCE ===')
print(f'Empty tasks IN audit results: {len(in_audit)}')
print(f'Empty tasks NOT in audit results: {len(not_in_audit)}')

# --- 4. Also check if empty tasks can be found by examining pre_live task_text ---
# Load pre_live to get mapping of original_id -> task_index
pre_live = json.load(
    open(r'../../Downloads/FORMYLA_CONDITION_COURT/runs/selection_1080_20260712_134037/curated_bank_L1_L5_pre_live.json',
         'r', encoding='utf-8'))

# Build original_id -> task mapping for pre_live
pre_by_oid = {}
for t in pre_live:
    oid = t.get('original_id', '')
    pre_by_oid[oid] = t

print(f'\n=== PRE_LIVE ANALYSIS ===')
print(f'pre_live count: {len(pre_live)}')

# Check empty tasks in pre_live
empty_with_pre = sum(1 for oid in empty_oids if oid in pre_by_oid)
print(f'Empty tasks that exist in pre_live: {empty_with_pre}')

# For a sample of empty tasks, show what's in pre_live
print('\nSample empty tasks (first 5) - task_text from pre_live:')
for i, t in enumerate(empty[:5]):
    oid = t.get('original_id', '')
    pre_t = pre_by_oid.get(oid, {})
    tt = pre_t.get('task_text', 'NO task_text')[:100]
    print(f'  {oid}: task_text="{tt}..."')

# --- 5. Check distinct topic distribution of empty tasks ---
from collections import Counter
empty_topics = Counter(t.get('topic', 'UNKNOWN') for t in empty)
print(f'\nTopic distribution of empty tasks (top 15):')
for topic, cnt in empty_topics.most_common(15):
    print(f'  {topic}: {cnt}')

# --- 6. Check what final_court_status says for empty tasks ---
empty_statuses = Counter(t.get('final_court_status', 'UNKNOWN') for t in empty)
print(f'\nfinal_court_status of empty tasks:')
for s, cnt in empty_statuses.most_common():
    print(f'  {s}: {cnt}')

# --- 7. Check which audit level_mismatches list has... 
# Are the empty tasks the ones that failed audit? ---
# Build set of task_indices that failed
if results:
    failed_indices = set()
    for r in results:
        verdict = r.get('verdict', '')
        if verdict in ('MAJOR', 'FAIL', 'BAD', 'failed'):
            failed_indices.add(r.get('task_index'))
    print(f'\nFailed audit task_indices: {len(failed_indices)}')

# Summary
lines = []
lines.append('=== FORENSIC SUMMARY: 250 empty tasks ===')
lines.append(f'Empty in fixed: {len(empty)}')
lines.append(f'Audit results entries: {len(results)}')
lines.append(f'Empty tasks in audit: {len(in_audit)}')
lines.append(f'Empty tasks NOT in audit: {len(not_in_audit)}')
lines.append(f'Empty tasks that exist in pre_live: {empty_with_pre}')
lines.append('')
lines.append('TOPIC DISTRIBUTION OF EMPTY TASKS:')
for topic, cnt in empty_topics.most_common(20):
    lines.append(f'  {topic}: {cnt}')
lines.append('')
lines.append('final_court_status of empty tasks:')
for s, cnt in empty_statuses.most_common():
    lines.append(f'  {s}: {cnt}')

open('_diag5_output.txt', 'w', encoding='utf-8').write('\n'.join(lines))
print('\nDONE - written to _diag5_output.txt')
