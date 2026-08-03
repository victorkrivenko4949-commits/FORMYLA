#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Apply deepseek-reasoner audit results to curated_bank_L1_L5_fixed.json.

Logic:
1. For L1-L3 tasks with MAJOR/MINOR level verdict -> adjust level based on suggested_level
2. For level=None tasks with L1-L3 target -> assign level based on audit or target_level
3. Save as curated_bank_L1_L5_fixed_AUDITED.json (backup original first)
"""
import json, sys, shutil, os
from collections import Counter

def log(msg):
    print(msg)
    sys.stdout.flush()

# ===== LOAD DATA =====
log("Loading curated_bank_L1_L5_fixed.json...")
bank = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))
log(f"Loaded {len(bank)} tasks")

log("Loading audit_l1_l3_results.json...")
audit = json.load(open('audit_l1_l3_results.json', 'r', encoding='utf-8'))
results = audit.get('results', [])
log(f"Loaded {len(results)} audit results")

# Map audit results by task_index
results_map = {}
for r in results:
    results_map[r.get('task_index')] = r

def get_level_verdict(r):
    ar = r.get('audit_result', {})
    lm = ar.get('level_match', {})
    return lm.get('verdict', '?'), lm.get('suggested_level')

def target_to_int(tl):
    """Convert 'L1' -> 1, 'L2' -> 2, etc."""
    if not tl:
        return None
    try:
        return int(tl.replace('L', ''))
    except:
        return None

# ===== BACKUP =====
backup_path = 'curated_bank_L1_L5_fixed_BEFORE_AUDIT.json'
if not os.path.exists(backup_path):
    shutil.copy2('curated_bank_L1_L5_fixed.json', backup_path)
    log(f"Backup saved to {backup_path}")
else:
    log(f"Backup already exists at {backup_path}")

# ===== STATS =====
stats = {
    'l13_adjusted': 0,
    'l13_adjusted_detail': [],
    'none_assigned': 0,
    'none_assigned_detail': [],
    'l13_unchanged_major_minor': 0,
    'errors': [],
}

# ===== PROCESS =====
changes_made = []
for i, t in enumerate(bank):
    si = t.get('source_index')
    if si is None:
        continue
    
    r = results_map.get(si)
    if r is None:
        stats['errors'].append(f"Task {t.get('original_id','?')}: source_index={si} not in audit")
        continue
    
    v, sl = get_level_verdict(r)
    current_level = t.get('level')
    target_level = t.get('target_level', '')
    tid = t.get('original_id', '?')
    
    # --- CASE 1: L1-L3 task with MAJOR/MINOR verdict ---
    if current_level in (1, 2, 3) and v in ('MAJOR', 'MINOR') and sl is not None:
        suggested_int = target_to_int(sl)
        if suggested_int and suggested_int != current_level:
            t['level'] = suggested_int
            if not isinstance(t.get('changes_made'), list):
                t['changes_made'] = []
            t['changes_made'].append(f"audit_fix: level {current_level}->{suggested_int} (verdict={v})")
            t['fixed_by_ai'] = True
            stats['l13_adjusted'] += 1
            stats['l13_adjusted_detail'].append({
                'id': tid,
                'old_level': current_level,
                'new_level': suggested_int,
                'verdict': v,
                'grade': t.get('grade'),
            })
            changes_made.append(f"{tid}: L{current_level}->L{suggested_int} (grade={t.get('grade')}, verdict={v})")
        elif suggested_int and suggested_int == current_level:
            # Verdict is MAJOR/MINOR but suggested_level matches current — leave it
            stats['l13_unchanged_major_minor'] += 1
    
    # --- CASE 2: Level=None with L1-L3 target ---
    elif current_level is None and target_level in ('L1', 'L2', 'L3'):
        target_int = target_to_int(target_level)
        
        if v == 'PASS':
            # Audit agrees — assign based on target_level
            t['level'] = target_int
            if not isinstance(t.get('changes_made'), list):
                t['changes_made'] = []
            t['changes_made'].append(f"level_assigned: None->{target_int} (audit=PASS)")
            t['fixed_by_ai'] = True
            stats['none_assigned'] += 1
            stats['none_assigned_detail'].append({
                'id': tid,
                'old_level': None,
                'new_level': target_int,
                'verdict': v,
                'grade': t.get('grade'),
            })
            changes_made.append(f"{tid}: None->L{target_int} (grade={t.get('grade')}, verdict=PASS)")
        elif v in ('MAJOR', 'MINOR') and sl is not None:
            # Audit found issue — use suggested_level
            suggested_int = target_to_int(sl)
            if suggested_int:
                t['level'] = suggested_int
                if not isinstance(t.get('changes_made'), list):
                    t['changes_made'] = []
                t['changes_made'].append(f"level_assigned: None->{suggested_int} (verdict={v}, suggested={sl})")
                t['fixed_by_ai'] = True
                stats['none_assigned'] += 1
                stats['none_assigned_detail'].append({
                    'id': tid,
                    'old_level': None,
                    'new_level': suggested_int,
                    'verdict': v,
                    'suggested': sl,
                    'grade': t.get('grade'),
                })
                changes_made.append(f"{tid}: None->L{suggested_int} (grade={t.get('grade')}, verdict={v}, suggested={sl})")
            else:
                # suggested_level is None but verdict is MAJOR/MINOR — fallback to target
                t['level'] = target_int
                if not isinstance(t.get('changes_made'), list):
                    t['changes_made'] = []
                t['changes_made'].append(f"level_assigned: None->{target_int} (by target, verdict={v})")
                t['fixed_by_ai'] = True
                stats['none_assigned'] += 1
                stats['none_assigned_detail'].append({
                    'id': tid,
                    'old_level': None,
                    'new_level': target_int,
                    'verdict': v,
                    'grade': t.get('grade'),
                })
                changes_made.append(f"{tid}: None->L{target_int} (grade={t.get('grade')}, verdict={v}, fallback to target)")

# ===== SUMMARY =====
log("\n========== CHANGES APPLIED ==========")
log(f"L1-L3 adjusted (MAJOR/MINOR): {stats['l13_adjusted']}")
log(f"Level=None assigned: {stats['none_assigned']}")
log(f"L1-L3 MAJOR/MINOR unchanged (suggested matches current): {stats['l13_unchanged_major_minor']}")
log(f"Errors: {len(stats['errors'])}")

log("\n--- L1-L3 adjustments ---")
for d in stats['l13_adjusted_detail']:
    log(f"  {d['id']}: L{d['old_level']}->L{d['new_level']} (grade={d['grade']}, verdict={d['verdict']})")

log("\n--- Level=None assignments ---")
for d in stats['none_assigned_detail']:
    log(f"  {d['id']}: None->L{d['new_level']} (grade={d['grade']}, verdict={d['verdict']})")

log("\n--- Errors ---")
for e in stats['errors']:
    log(f"  ERROR: {e}")

# ===== VERIFY RESULTS =====
log("\n========== VERIFICATION ==========")
levels_after = Counter(str(t.get('level')) for t in bank)
log(f"Levels after: {dict(sorted(levels_after.items()))}")

l13_after = [t for t in bank if t.get('level') in (1, 2, 3)]
log(f"L1-L3 count after: {len(l13_after)}")

none_after = [t for t in bank if t.get('level') is None]
log(f"Level=None count after: {len(none_after)}")
if none_after:
    tl_none = Counter(str(t.get('target_level', '?')) for t in none_after)
    log(f"  Remaining None by target_level: {dict(tl_none)}")

# ===== SAVE =====
output_path = 'curated_bank_L1_L5_fixed.json'
log(f"\nSaving to {output_path}...")
json.dump(bank, open(output_path, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
log("Done!")
