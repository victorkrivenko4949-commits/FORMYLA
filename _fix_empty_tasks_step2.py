#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Step 2: Merge task_XXX regenerations into fixed.json using task_index mapping.
85 regenerations had task_XXX format IDs (task_25 instead of SEL1080-XXXX).
The original merge matched by original_id, so these 85 were skipped.
Fix: use task_index -> fixed.json array index to apply regeneration content.
"""
import json
from collections import Counter
from datetime import datetime, timezone

fixed = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))
regen = json.load(open('_regenerated_675_tasks.json', 'r', encoding='utf-8'))
audit = json.load(open('audit_675_full_results.json', 'r', encoding='utf-8'))

print('=== STEP 2: MERGE task_XXX REGENERATIONS VIA task_index ===')

# 1. Find all regenerated results with task_XXX format IDs
results = regen.get('results', [])
task_xxx_regens = [r for r in results if str(r.get('source_task', {}).get('original_id', '')).startswith('task_')]
print(f'\nRegen results with task_XXX IDs: {len(task_xxx_regens)} out of {len(results)} total')

# 2. For each, check if fixed.json entry at task_index is empty, and merge
ts = datetime.now(timezone.utc).isoformat()
merged_count = 0
already_filled = 0
failed_no_fixed = 0
for r in task_xxx_regens:
    ti = r.get('task_index')
    if ti is None or ti >= len(fixed):
        print(f'  SKIP: task_index={ti} out of range')
        continue
    
    ft = fixed[ti]
    if ft.get('statement'):
        already_filled += 1
        continue  # Already has content
    
    # Entry is empty - merge fixed_task fields
    fixed_task = r.get('fixed_task', {})
    if not fixed_task or not r.get('success', False):
        failed_no_fixed += 1
        continue
    
    for field in ['statement', 'answer', 'solution', 'level', 'grade', 'topic']:
        if field in fixed_task:
            ft[field] = fixed_task[field]
    ft['fixed_by_ai'] = True
    ft['fix_timestamp'] = r.get('regeneration_timestamp', ts)
    ft['changes_made'] = r.get('changes_made', [])
    merged_count += 1

print(f'\nMerge results:')
print(f'  Merged (was empty, now filled): {merged_count}')
print(f'  Already filled (skipped): {already_filled}')
print(f'  Failed/skipped (no fixed_task): {failed_no_fixed}')
print(f'  Total task_XXX: {len(task_xxx_regens)}')

# 3. Count remaining empty tasks
empty_now = [t for t in fixed if not t.get('statement')]
print(f'\n=== AFTER STEP 2 MERGE: {len(empty_now)} tasks still empty ===')
print(f'  Filled in this step: {merged_count}')

# 4. Categorize remaining empty by audit verdict
oid_to_idx = {t.get('original_id', ''): i for i, t in enumerate(fixed)}
audit_results_list = audit.get('results', [])
audit_by_index = {}
for r in audit_results_list:
    ti = r.get('task_index')
    if ti is not None:
        audit_by_index[ti] = {
            'verdict': r.get('pipeline_verdict', 'UNKNOWN'),
            'success': r.get('success', True)
        }

empty_verdicts = Counter()
empty_no_audit = 0
empty_list = []
for t in empty_now:
    oid = t.get('original_id', '')
    idx = oid_to_idx.get(oid)
    if idx is not None and idx in audit_by_index:
        v = audit_by_index[idx]['verdict']
        empty_verdicts[v] += 1
        empty_list.append((idx, oid, v, t.get('topic', '?'), t.get('task_text', '')[:80]))
    else:
        empty_no_audit += 1
        empty_list.append((idx or -1, oid, 'NO_AUDIT', t.get('topic', '?'), t.get('task_text', '')[:80]))

print(f'\nRemaining empty tasks by audit verdict:')
for v, c in empty_verdicts.most_common():
    print(f'  {v}: {c}')
if empty_no_audit:
    print(f'  NO_AUDIT: {empty_no_audit}')

# 5. Save updated fixed.json
json.dump(fixed, open('curated_bank_L1_L5_fixed.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'\nSaved updated curated_bank_L1_L5_fixed.json')

# 6. Generate tasks_needing_regeneration.json
need_regen = []
for idx, oid, verdict, topic, txt in empty_list:
    need_regen.append({
        'index': idx,
        'original_id': oid,
        'audit_verdict': verdict,
        'topic': topic,
        'task_text_hint': txt
    })

json.dump(need_regen, open('_tasks_needing_regeneration.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'\nGenerated _tasks_needing_regeneration.json: {len(need_regen)} tasks need AI regeneration')
print('\nDone step 2.')
