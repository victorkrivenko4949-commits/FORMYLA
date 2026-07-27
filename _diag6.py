#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Final cross-reference: audit task_index -> fixed tasks, using pre_live order."""
import json
from collections import Counter

fixed = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))
pre_live = json.load(
    open(r'../../Downloads/FORMYLA_CONDITION_COURT/runs/selection_1080_20260712_134037/curated_bank_L1_L5_pre_live.json',
         'r', encoding='utf-8'))
audit = json.load(open('audit_675_full_results.json', 'r', encoding='utf-8'))

# --- 1. Map pre_live index (order) -> original_id ---
index_to_oid = {}
oid_to_index = {}
for i, t in enumerate(pre_live):
    oid = t.get('original_id', '')
    index_to_oid[i] = oid
    oid_to_index[oid] = i

print(f'pre_live: {len(pre_live)} tasks, index range 0-{len(pre_live)-1}')

# --- 2. Build set of audited original_ids ---
results = audit.get('results', [])
audited_indices = set()
for r in results:
    ti = r.get('task_index')
    if ti is not None:
        audited_indices.add(ti)

print(f'Audited task_indices: {len(audited_indices)}')
print(f'Range: {min(audited_indices)}-{max(audited_indices)}')

# Map audited indices to original_ids
audited_oids = set()
for idx in audited_indices:
    oid = index_to_oid.get(idx, '')
    if oid:
        audited_oids.add(oid)

print(f'Audited original_ids: {len(audited_oids)}')

# --- 3. Check fixed tasks ---
empty = [t for t in fixed if not t.get('statement')]
filled = [t for t in fixed if t.get('statement')]

print(f'\nFixed: {len(fixed)} total')
print(f'Empty: {len(empty)}')
print(f'Filled: {len(filled)}')

# final_court_status distribution
empty_statuses = Counter(t.get('final_court_status', 'UNKNOWN') for t in empty)
filled_statuses = Counter(t.get('final_court_status', 'UNKNOWN') for t in filled)
print(f'\nEmpty final_court_status: {dict(empty_statuses)}')
print(f'Filled final_court_status: {dict(filled_statuses)}')

# --- 4. Check if empty tasks' original_ids were audited ---
empty_oids = set(t.get('original_id', '') for t in empty)
filled_oids = set(t.get('original_id', '') for t in filled)

empty_in_audit = empty_oids & audited_oids
empty_not_in_audit = empty_oids - audited_oids
filled_in_audit = filled_oids & audited_oids
filled_not_in_audit = filled_oids - audited_oids

print(f'\n=== AUDIT COVERAGE ===')
print(f'Empty tasks IN audit:       {len(empty_in_audit)}')
print(f'Empty tasks NOT in audit:   {len(empty_not_in_audit)}')
print(f'Filled tasks IN audit:      {len(filled_in_audit)}')
print(f'Filled tasks NOT in audit:  {len(filled_not_in_audit)}')

# --- 5. For filled tasks NOT in audit: where did they come from? ---
if filled_not_in_audit:
    print(f'\n=== FILLED BUT NOT AUDITED ===')
    print(f'Count: {len(filled_not_in_audit)}')
    # Show first 10 examples
    for i, oid in enumerate(sorted(filled_not_in_audit)[:10]):
        t = next(t for t in filled if t.get('original_id') == oid)
        print(f'  {oid}: topic={t.get("topic","?")}, level={t.get("level","?")}, changes_made={t.get("changes_made",[])}')

# --- 6. Check changes_made on empty vs filled ---
empty_changes = sum(1 for t in empty if t.get('changes_made'))
filled_changes = sum(1 for t in filled if t.get('changes_made'))
print(f'\n=== CHANGES_MADE ===')
print(f'Empty with changes_made: {empty_changes}')
print(f'Filled with changes_made: {filled_changes}')

# --- 7. Check what source says for both groups ---
empty_source = Counter(t.get('source', 'MISSING') for t in empty)
filled_source = Counter(t.get('source', 'MISSING') for t in filled)
print(f'\n=== SOURCE ===')
print(f'Empty source: {dict(empty_source)}')
print(f'Filled source: {dict(filled_source)}')

# --- 8. Check fixed_by_ai ---
empty_fixed = sum(1 for t in empty if t.get('fixed_by_ai'))
filled_fixed = sum(1 for t in filled if t.get('fixed_by_ai'))
print(f'\n=== FIXED_BY_AI ===')
print(f'Empty with fixed_by_ai: {empty_fixed}')
print(f'Filled with fixed_by_ai: {filled_fixed}')

# --- 9. Check which tasks have audit_result.success=False in the audit data ---
# Build audit verdict per oid
audit_verdict = {}
for r in results:
    ti = r.get('task_index')
    oid = index_to_oid.get(ti, '')
    verdict = r.get('pipeline_verdict', r.get('verdict', 'UNKNOWN'))
    success = r.get('success', True)
    audit_verdict[oid] = {'verdict': verdict, 'success': success}

# Check verdict distribution for filled tasks
filled_verdicts = Counter()
for oid in filled_oids:
    if oid in audit_verdict:
        filled_verdicts[audit_verdict[oid]['verdict']] += 1
    else:
        filled_verdicts['NO_AUDIT_RESULT'] += 1

print(f'\n=== FILLED TASKS: AUDIT VERDICT ===')
for v, cnt in filled_verdicts.most_common():
    print(f'  {v}: {cnt}')

# --- 10. Check what happens with the original 1080 IDs ---
all_oids = set(t.get('original_id', '') for t in fixed)
print(f'\n=== ID ANALYSIS ===')
# Extract numeric parts
import re
nums = []
for oid in all_oids:
    m = re.search(r'SEL1080-(\d+)', str(oid))
    if m:
        nums.append(int(m.group(1)))
nums.sort()
print(f'ID range: {min(nums)}-{max(nums)} (out of 1..1080)')
print(f'Unique IDs: {len(nums)}')
# Find gaps
all_possible = set(range(1, 1081))
present = set(nums)
missing = sorted(all_possible - present)
print(f'Missing IDs: {len(missing)}')
print(f'First 20 missing: {missing[:20]}')
print(f'Last 20 missing: {missing[-20:]}')

# --- 11. Summary ---
lines = []
lines.append('=== DIAG6 FORENSIC SUMMARY ===')
lines.append(f'Fixed total: {len(fixed)}')
lines.append(f'pre_live total: {len(pre_live)}')
lines.append(f'Audit results entries: {len(results)}')
lines.append(f'Audit unique task_indices: {len(audited_indices)}')
lines.append(f'')
lines.append(f'Empty tasks: {len(empty)}')
lines.append(f'  final_court_status: {dict(empty_statuses)}')
lines.append(f'  In audit: {len(empty_in_audit)}')
lines.append(f'  Not in audit: {len(empty_not_in_audit)}')
lines.append(f'')
lines.append(f'Filled tasks: {len(filled)}')
lines.append(f'  final_court_status: {dict(filled_statuses)}')
lines.append(f'  In audit: {len(filled_in_audit)}')
lines.append(f'  Not in audit: {len(filled_not_in_audit)}')
lines.append(f'')
lines.append(f'Filled verdicts:')
for v, cnt in filled_verdicts.most_common():
    lines.append(f'  {v}: {cnt}')
lines.append(f'')
lines.append(f'Missing IDs from 1..1080: {len(missing)}')
lines.append(f'First 20 missing: {missing[:20]}')

open('_diag6_output.txt', 'w', encoding='utf-8').write('\n'.join(lines))
print('\nDONE')
