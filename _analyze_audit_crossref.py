#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cross-reference audit results with curated bank L1-L3 tasks."""
import json, sys
from collections import Counter

def log(msg):
    print(msg)
    sys.stdout.flush()

log("Loading curated_bank_L1_L5_fixed.json...")
bank = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))
log(f"Loaded {len(bank)} tasks")

log("\nLoading audit_l1_l3_results.json...")
audit = json.load(open('audit_l1_l3_results.json', 'r', encoding='utf-8'))
log(f"Audit keys: {list(audit.keys())}")

# --- Check results structure ---
results = audit.get('results', [])
log(f"Audit results count: {len(results)}")

# Check full structure of first result
r0 = results[0]
ar = r0.get('audit_result', {})
log(f"audit_result keys: {list(ar.keys())}")
lm = ar.get('level_match', {})
log(f"level_match keys: {list(lm.keys())}")
log(f"level_match.verdict = {lm.get('verdict')}")
log(f"level_match.suggested_level = {lm.get('suggested_level')}")
log(f"overall verdict = {ar.get('overall')}")
log(f"Full first result: {json.dumps(r0, indent=2, ensure_ascii=False)[:2000]}")

# --- Map results by task_index ---
results_map = {}
for r in results:
    results_map[r.get('task_index')] = r

log(f"\nUnique task_indices in results: {len(results_map)}")

# --- Cross-reference with curated bank ---
l13_idx = set()
l13_none_idx = set()
all_idx = set()

for t in bank:
    si = t.get('source_index')
    if si is None:
        continue
    all_idx.add(si)
    if t.get('level') in (1, 2, 3):
        l13_idx.add(si)
    elif t.get('level') is None:
        tl = t.get('target_level', '')
        if tl in ('L1', 'L2', 'L3'):
            l13_none_idx.add(si)

log(f"\n=== CROSS-REFERENCE ===")
log(f"Curated bank unique source_indices: {len(all_idx)}")
log(f"L1-L3 (level=1/2/3): {len(l13_idx)}")
log(f"Level=None (L1-L3 by target): {len(l13_none_idx)}")

matched_l13 = l13_idx & set(results_map.keys())
matched_none = l13_none_idx & set(results_map.keys())

log(f"\nL1-L3 with audit verdict: {len(matched_l13)}/{len(l13_idx)}")
log(f"Level=None (L1-L3 target) with audit verdict: {len(matched_none)}/{len(l13_none_idx)}")

# --- Parse nested verdicts ---
def get_level_verdict(r):
    """Extract level_match verdict and suggested_level."""
    ar = r.get('audit_result', {})
    lm = ar.get('level_match', {})
    return lm.get('verdict', '?'), lm.get('suggested_level')

def get_overall_verdict(r):
    ar = r.get('audit_result', {})
    return ar.get('overall', '?')

# --- Level verdict distribution ---
v_l13 = Counter()
v_none = Counter()
sl_l13 = Counter()
sl_none = Counter()

for si in matched_l13:
    v, sl = get_level_verdict(results_map[si])
    v_l13[v] += 1
    if sl:
        sl_l13[sl] += 1

for si in matched_none:
    v, sl = get_level_verdict(results_map[si])
    v_none[v] += 1
    if sl:
        sl_none[sl] += 1

log(f"\n=== LEVEL VERDICT DISTRIBUTION (L1-L3) ===")
log(f"Level verdicts: {dict(v_l13)}")
log(f"Suggested levels: {dict(sl_l13)}")

log(f"\n=== LEVEL VERDICT DISTRIBUTION (Level=None, target L1-L3) ===")
log(f"Level verdicts: {dict(v_none)}")
log(f"Suggested levels: {dict(sl_none)}")

# --- Detailed breakdown by grade+level ---
log(f"\n=== DETAILED BREAKDOWN BY CELL (L1-L3 with audit) ===")
gl_detail = {}
for t in bank:
    si = t.get('source_index')
    if si is None:
        continue
    if t.get('level') not in (1, 2, 3):
        continue
    g = t.get('grade', '?')
    l = t.get('level', '?')
    ck = f"G{g}|L{l}"
    r = results_map.get(si)
    if r is None:
        continue
    v, sl = get_level_verdict(r)
    gl_detail.setdefault(ck, Counter())
    gl_detail[ck][v] += 1

for ck in sorted(gl_detail.keys()):
    dist = dict(gl_detail[ck])
    total = sum(gl_detail[ck].values())
    log(f"  {ck}: {total} tasks -> {dist}")

# --- MAJOR/MINOR breakdown ---
log(f"\n=== MAJOR/MINOR VERDICTS (L1-L3) ===")
major_minor = {k: v for k, v in v_l13.items() if k in ('MAJOR', 'MINOR')}
log(f"Total MAJOR+MINOR: {sum(major_minor.values())}")
for v, cnt in sorted(major_minor.items()):
    log(f"  {v}: {cnt}")

# --- List MAJOR/MINOR tasks ---
log(f"\n=== SAMPLE MAJOR/MINOR TASKS (first 20) ===")
count = 0
for t in bank:
    if count >= 20:
        break
    si = t.get('source_index')
    if si is None:
        continue
    if t.get('level') not in (1, 2, 3):
        continue
    r = results_map.get(si)
    if r is None:
        continue
    v, sl = get_level_verdict(r)
    if v in ('MAJOR', 'MINOR'):
        count += 1
        tid = t.get('original_id', '?')
        log(f"  {tid}: verdict={v}, suggested_level={sl}, current_level={t.get('level')}, grade={t.get('grade')}")

# --- OVERALL verdict distribution ---
o_l13 = Counter()
for si in matched_l13:
    ov = get_overall_verdict(results_map[si])
    o_l13[ov] += 1

log(f"\n=== OVERALL VERDICT DISTRIBUTION (L1-L3) ===")
log(f"Overall verdicts: {dict(o_l13)}")

# --- Summary ---
log("\n\n========== SUMMARY ==========")
log(f"Total curated bank: {len(bank)}")
log(f"L1-L3 (by level field): {len(l13_idx)}")
log(f"  - with audit results: {len(matched_l13)}")
log(f"Level=None with L1-L3 target: {len(l13_none_idx)}")
log(f"  - with audit results: {len(matched_none)}")
log(f"L1-L3 level verdicts: {dict(v_l13)}")
log(f"Level=None level verdicts: {dict(v_none)}")
if 'MAJOR' in v_l13 or 'MINOR' in v_l13:
    log(f"L1-L3 tasks needing attention (MAJOR/MINOR): {v_l13.get('MAJOR',0) + v_l13.get('MINOR',0)}")
else:
    log("L1-L3: No MAJOR/MINOR verdicts found")
log(f"L1-L3 suggested levels (non-None): {dict(sl_l13)}")
