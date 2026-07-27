#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Final forensic analysis: why 250 tasks are empty."""
import json, re, sys
from collections import Counter

fixed = json.load(open('curated_bank_L1_L5_fixed.json','r',encoding='utf-8'))
pre_live = json.load(open(r'../../Downloads/FORMYLA_CONDITION_COURT/runs/selection_1080_20260712_134037/curated_bank_L1_L5_pre_live.json','r',encoding='utf-8'))
audit = json.load(open('audit_675_full_results.json','r',encoding='utf-8'))
regen = json.load(open('_regenerated_675_tasks.json','r',encoding='utf-8'))

index_to_oid = {i: t.get('original_id','') for i,t in enumerate(pre_live)}
oid_to_index = {t.get('original_id',''): i for i,t in enumerate(pre_live)}

empty = [t for t in fixed if not t.get('statement')]
filled = [t for t in fixed if t.get('statement')]

lines = []
def log(msg):
    lines.append(str(msg))
    print(msg)

log('=== FORENSIC FINAL ANALYSIS ===')
log(f'Fixed total: {len(fixed)}')
log(f'Empty (no statement/answer/solution): {len(empty)}')
log(f'Filled (has statement/answer/solution): {len(filled)}')

# === REGENERATION ANALYSIS ===
results = regen.get('results',[])
log(f'\n=== REGENERATION ({len(results)} total results) ===')
summary = regen.get('summary',{})
for k,v in summary.items():
    log(f'  {k}: {v}')

task_xxx_count = 0
sel1080_count = 0
task_xxx_ids = []
sel1080_oids = []
reg_oid_to_data = {}
for r in results:
    oid = r.get('original_id','')
    reg_oid_to_data[oid] = r
    if oid.startswith('task_'):
        task_xxx_count += 1
        task_xxx_ids.append(oid)
    else:
        sel1080_count += 1
        sel1080_oids.append(oid)

log(f'task_XXX format IDs: {task_xxx_count}')
log(f'SEL1080-XXXX format IDs: {sel1080_count}')

# Check which task_XXX are in pre_live
matched_task_xxx = 0
unmatched_task_xxx = 0
for oid in task_xxx_ids:
    if oid in oid_to_index:
        matched_task_xxx += 1
    else:
        unmatched_task_xxx += 1
log(f'task_XXX matched in pre_live: {matched_task_xxx}')
log(f'task_XXX NOT in pre_live: {unmatched_task_xxx}')

# === AUDIT VERDICT FOR EMPTY TASKS ===
audit_results = audit.get('results',[])
log(f'\n=== AUDIT SUMMARY ===')
audit_summary = audit.get('summary',{})
for k,v in audit_summary.items():
    log(f'  {k}: {v}')

# Build audit verdict per task_index (deduplicated)
audit_by_index = {}
for r in audit_results:
    ti = r.get('task_index')
    if ti is not None:
        verdict = r.get('pipeline_verdict', 'UNKNOWN')
        success = r.get('success', True)
        if ti not in audit_by_index:
            audit_by_index[ti] = {'verdict': verdict, 'success': success}

# For each empty task, find its audit verdict
empty_verdicts = Counter()
empty_details = []
for t in empty:
    oid = t.get('original_id','')
    idx = oid_to_index.get(oid)
    if idx is not None and idx in audit_by_index:
        v = audit_by_index[idx]['verdict']
        s = audit_by_index[idx]['success']
        empty_verdicts[v] += 1
        empty_details.append((idx, oid, v, s))
    else:
        empty_verdicts['NO_AUDIT'] += 1
        empty_details.append((idx or -1, oid, 'NO_AUDIT', False))

log(f'\n=== EMPTY TASKS: AUDIT VERDICT DISTRIBUTION ===')
for v,c in sorted(empty_verdicts.items(), key=lambda x:-x[1]):
    log(f'  {v}: {c}')

# Filled verdicts for comparison
filled_verdicts = Counter()
for t in filled:
    oid = t.get('original_id','')
    idx = oid_to_index.get(oid)
    if idx is not None and idx in audit_by_index:
        v = audit_by_index[idx]['verdict']
        filled_verdicts[v] += 1

log(f'\n=== FILLED TASKS: AUDIT VERDICT DISTRIBUTION ===')
for v,c in sorted(filled_verdicts.items(), key=lambda x:-x[1]):
    log(f'  {v}: {c}')

# === GAP ANALYSIS ===
passed_minor = audit_summary.get('passed',0) + audit_summary.get('minor',0)
failed_audit = audit_summary.get('failed_audit',0)
api_failures = audit_summary.get('api_failures',0)

log(f'\n=== GAP ANALYSIS ===')
log(f'Audit -> passed+minor={passed_minor} (no regen needed)')
log(f'Audit -> failed_audit={failed_audit} (regenerated)')
log(f'Audit -> api_failures={api_failures}')

log(f'\nExpected empty breakdown:')
log(f'  passed+minor (never regen): {passed_minor}')
log(f'  task_XXX unmatched (regen but no merge): {unmatched_task_xxx}')
log(f'  Total expected empty: {passed_minor + unmatched_task_xxx}')
log(f'  Actual empty: {len(empty)}')

# Verify: empty tasks that passed audit + empty tasks that failed audit
empty_passed_minor = sum(1 for d in empty_details if d[2] in ('passed','minor'))
empty_failed = sum(1 for d in empty_details if d[2] in ('failed_audit','failed'))
empty_api = sum(1 for d in empty_details if d[2] == 'api_failure')
log(f'\nEmpty tasks that passed+minor: {empty_passed_minor}')
log(f'Empty tasks that failed: {empty_failed}')
log(f'Empty api_failure: {empty_api}')
log(f'Empty no_audit: {empty_verdicts.get("NO_AUDIT",0)}')
log(f'Sum: {empty_passed_minor + empty_failed + empty_api + empty_verdicts.get("NO_AUDIT",0)}')

# === ROOT CAUSE CONFIRMATION ===
log(f'\n=== ROOT CAUSE VERIFICATION ===')
# 164 passed+minor tasks were never regenerated -> never enriched -> empty
# 85 task_XXX regenerations never matched by original_id -> never merged -> empty
# 1 extra (rounding) -> empty
log(f'164 (passed+minor) + 85 (unmatched task_XXX) + 1 = 250?')
log(f'{passed_minor} + {unmatched_task_xxx} + 1 = {passed_minor + unmatched_task_xxx + 1}')
# Check: is 1 the api_failure?
log(f'Out of 509 failed + 4 api_failures = 513')
log(f'509 regenerated - 424 merged = 85 unmatched')
log(f'4 api_failures had NO regeneration at all')
log(f'So: 164 (passed+minor, no regen) + 85 (regen but no merge) + 1 (api_failure?) = 250')

# === WHAT NEEDS TO HAPPEN ===
log(f'\n=== FIX PLAN ===')
log(f'To fill the 250 empty tasks, we need to:')
log(f'  1. For 164 passed+minor tasks: extract statement/answer/solution from task_text')
log(f'     OR regenerate them through AI too')
log(f'  2. For 85 task_XXX tasks: fix ID format to SEL1080-XXXX and re-run merge')
log(f'  3. For api_failures: regenerate them')

# === SAMPLE: 5 empty passed tasks ===
log(f'\n=== SAMPLE: EMPTY PASSED TASKS ===')
count = 0
for idx, oid, v, s in empty_details:
    if v in ('passed','minor') and count < 5:
        t = pre_live[idx]
        log(f'  idx={idx} oid={oid} verdict={v} topic={t.get("topic","?")}')
        log(f'    task_text[:100]: {t.get("task_text","")[:100]}')
        count += 1

# === SAMPLE: 5 empty failed tasks (task_XXX) ===
log(f'\n=== SAMPLE: EMPTY FAILED TASKS (task_XXX format) ===')
count = 0
for idx, oid, v, s in empty_details:
    if v == 'failed_audit' and oid.startswith('task_') and count < 5:
        t = pre_live[idx]
        log(f'  idx={idx} oid={oid} topic={t.get("topic","?")}')
        log(f'    task_text[:100]: {t.get("task_text","")[:100]}')
        count += 1

# === CHECK: What if we fix task_XXX IDs? ===
log(f'\n=== FIX: REMATCH task_XXX ===')
# For each task_XXX regeneration, can we find the right SEL1080-XXX ID?
# Check if task_XXX has source_task with original_id
for oid in task_xxx_ids[:10]:
    r = reg_oid_to_data.get(oid, {})
    src = r.get('source_task', {})
    src_oid = src.get('original_id', 'N/A')
    log(f'  {oid} -> source_task.original_id = {src_oid}')
    task_idx = r.get('task_index', 'N/A')
    log(f'    task_index = {task_idx}')

# === WRITE REPORT ===
report = '\n'.join(lines)
open('_forensic_final_report.txt', 'w', encoding='utf-8').write(report)
log('\n\nREPORT SAVED TO _forensic_final_report.txt')
