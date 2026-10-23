#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Step 1: Fix the 85 task_XXX IDs and merge existing regenerated content.
"""
import json, re
from collections import Counter
from datetime import datetime, timezone

fixed = json.load(open('curated_bank_L1_L5_fixed.json','r',encoding='utf-8'))
pre_live = json.load(open(r'../../Downloads/FORMYLA_CONDITION_COURT/runs/selection_1080_20260712_134037/curated_bank_L1_L5_pre_live.json','r',encoding='utf-8'))
regen = json.load(open('_regenerated_675_tasks.json','r',encoding='utf-8'))
audit = json.load(open('audit_675_full_results.json','r',encoding='utf-8'))

print('=== STEP 1: FIX task_XXX IDs & MERGE EXISTING REGENERATIONS ===')

# --- 1. Find all task_XXX in pre_live ---
task_xxx_entries = [(i, t) for i, t in enumerate(pre_live) if str(t.get('original_id','')).startswith('task_')]
print(f'\ntask_XXX entries in pre_live: {len(task_xxx_entries)}')
for idx, t in task_xxx_entries[:5]:
    print(f'  idx={idx} oid={t.get("original_id","")} topic={t.get("topic","?")}')

# --- 2. Find available SEL1080 IDs ---
used_ids = set()
for t in pre_live:
    oid = t.get('original_id', '')
    if oid and not str(oid).startswith('task_'):
        used_ids.add(oid)
used_nums = set()
for oid in used_ids:
    m = re.search(r'SEL1080-(\d+)', str(oid))
    if m:
        used_nums.add(int(m.group(1)))
available_nums = sorted(set(range(1, 1081)) - used_nums)
print(f'\nSEL1080 IDs already used: {len(used_nums)}')
print(f'Available SEL1080 IDs: {len(available_nums)} first={available_nums[:5]} last={available_nums[-5:]}')

# --- 3. Build task_index -> regenerated result ---
regen_results = regen.get('results', [])
task_index_to_regen = {}
task_xxx_regen_count = 0
for r in regen_results:
    oid = r.get('original_id', '')
    ti = r.get('task_index')
    if str(oid).startswith('task_') and ti is not None:
        task_xxx_regen_count += 1
        task_index_to_regen[ti] = r
print(f'Regenerated results with task_XXX IDs: {task_xxx_regen_count}')

# --- 4. Merge: for each task_XXX, assign new ID and apply fixed_task ---
merge_applied = 0
merge_no_fixed = 0
merge_id_only = 0
now_ts = datetime.now(timezone.utc).isoformat()

for idx, t in task_xxx_entries:
    old_oid = t.get('original_id', '')
    new_num = available_nums.pop(0)
    new_oid = f'SEL1080-{new_num:04d}'
    
    # Update pre_live entry
    t['original_id'] = new_oid
    # Update fixed entry (same index as pre_live)
    ft = fixed[idx]
    ft['original_id'] = new_oid
    
    # Check if regenerated
    if idx in task_index_to_regen:
        r = task_index_to_regen[idx]
        fixed_task = r.get('fixed_task', {})
        if fixed_task and r.get('success', False):
            for field in ['statement', 'answer', 'solution', 'level', 'grade', 'topic']:
                if field in fixed_task:
                    ft[field] = fixed_task[field]
            ft['fixed_by_ai'] = True
            ft['fix_timestamp'] = r.get('regeneration_timestamp', now_ts)
            ft['changes_made'] = r.get('changes_made', [])
            merge_applied += 1
        else:
            merge_no_fixed += 1
    else:
        merge_id_only += 1

print(f'\nMerge results:')
print(f'  Applied (regenerated content merged): {merge_applied}')
print(f'  Regenerated but no fixed_task: {merge_no_fixed}')
print(f'  ID only (no regeneration): {merge_id_only}')
print(f'  Total task_XXX: {merge_applied + merge_no_fixed + merge_id_only}')

# --- 5. Count remaining empty tasks ---
empty_now = [t for t in fixed if not t.get('statement')]
print(f'\n=== AFTER MERGE: {len(empty_now)} tasks still empty ===')

# --- 6. Categorize remaining empty by audit verdict ---
oid_to_idx = {t.get('original_id',''): i for i,t in enumerate(pre_live)}
audit_results_list = audit.get('results', [])
audit_by_index = {}
for r in audit_results_list:
    ti = r.get('task_index')
    if ti is not None and ti not in audit_by_index:
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
        empty_list.append((idx, oid, v, t.get('topic','?'), t.get('task_text','')[:80]))
    else:
        empty_no_audit += 1
        empty_list.append((idx or -1, oid, 'NO_AUDIT', t.get('topic','?'), t.get('task_text','')[:80]))

print(f'\nEmpty tasks by audit verdict:')
for v,c in empty_verdicts.most_common():
    print(f'  {v}: {c}')
if empty_no_audit:
    print(f'  NO_AUDIT: {empty_no_audit}')

# --- 7. Save updated fixed.json ---
json.dump(fixed, open('curated_bank_L1_L5_fixed.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'\nSaved updated fixed.json with {merge_applied} merged tasks')

# --- 8. Generate list of tasks that still need AI regeneration ---
need_regen = []
for idx, oid, verdict, topic, txt in empty_list:
    need_regen.append({
        'index': idx,
        'original_id': oid,
        'audit_verdict': verdict,
        'topic': topic,
        'task_text': txt
    })

json.dump(need_regen, open('_tasks_needing_regeneration.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'Generated _tasks_needing_regeneration.json: {len(need_regen)} tasks need AI regeneration')
print('\nDone step 1.')
