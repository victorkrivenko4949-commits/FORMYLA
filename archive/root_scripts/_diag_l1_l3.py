#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Diagnose current state of L1-L3 in curated_bank_L1_L5_fixed.json"""
import json, sys
from collections import Counter

bank = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))

def log(msg):
    print(msg)
    sys.stdout.flush()

log('=== CURATED BANK L1-L5 OVERVIEW ===')
log(f'Total tasks: {len(bank)}')

levels = Counter(str(t.get('level')) for t in bank)
log(f'By level (field "level"): {dict(sorted(levels.items()))}')

target_levels = Counter(str(t.get('target_level')) for t in bank)
log(f'By target_level: {dict(sorted(target_levels.items()))}')

grades = Counter(str(t.get('grade')) for t in bank)
log(f'By grade: {dict(sorted(grades.items()))}')

# L1-L3 by level field
l13 = [t for t in bank if t.get('level') in (1, 2, 3)]
log(f'\n=== L1-L3 TASKS (by level=1/2/3) ===')
log(f'Count: {len(l13)}')
log(f'By level: {dict(sorted(Counter(t["level"] for t in l13).items()))}')
log(f'By grade: {dict(sorted(Counter(str(t.get("grade", "?")) for t in l13).items()))}')

# L1-L3 by target_level
l13_target = [t for t in bank if t.get('target_level') in ('L1', 'L2', 'L3')]
log(f'\n=== L1-L3 BY target_level ===')
log(f'Count: {len(l13_target)}')
log(f'By target_level: {dict(sorted(Counter(t.get("target_level", "?") for t in l13_target).items()))}')

# Tasks with target_level=L1/L2/L3 but level!=1/2/3
not_in_l13 = [t for t in l13_target if t.get('level') not in (1, 2, 3)]
log(f'\nTasks with target_level=L1/L2/L3 but level!=(1,2,3): {len(not_in_l13)}')
for t in not_in_l13[:10]:
    log(f'  id={t.get("original_id","?")} level={t.get("level")} target={t.get("target_level")} grade={t.get("grade")}')

# Level=None tasks
none_level = [t for t in bank if t.get('level') is None or str(t.get('level')) == 'None']
log(f'\n=== LEVEL=None TASKS ===')
log(f'Count: {len(none_level)}')
if none_level:
    tl_none = Counter(str(t.get('target_level', '?')) for t in none_level)
    log(f'By target_level: {dict(tl_none)}')
    g_none = Counter(str(t.get('grade', '?')) for t in none_level)
    log(f'By grade: {dict(g_none)}')

# ===== CELL ANALYSIS =====
log(f'\n=== CELL ANALYSIS (L1-L3 by level field) ===')
first = l13[0] if l13 else {}
log(f'Fields available: {list(first.keys())[:15]}...')

# Check for theme_id, subtopic_idx fields
has_theme = 'theme_id' in first or 'theme' in first
has_subtopic = 'subtopic_idx' in first or 'subtopic' in first
log(f'Has theme_id/theme: {has_theme}, has subtopic_idx/subtopic: {has_subtopic}')

# Use grade+level as cell key (since theme/subtopic might be missing)
cells = {}
for t in l13:
    g = t.get('grade', '?')
    l = t.get('level', '?')
    tid = t.get('theme_id') or t.get('theme', '?')
    sid = t.get('subtopic_idx') or t.get('subtopic', '?')
    ck = f'G{g}|L{l}|T{tid}|S{sid}'
    cells.setdefault(ck, []).append(t)

log(f'Unique cells: {len(cells)}')
fill_dist = Counter(len(tasks) for tasks in cells.values())
log(f'Fill distribution: {dict(sorted(fill_dist.items()))}')

# Under-filled (< 5)
under = {k: v for k, v in cells.items() if len(v) < 5}
if under:
    log(f'\nUNDER-FILLED CELLS ({len(under)}):')
    for ck, tasks in sorted(under.items()):
        log(f'  {ck}: {len(tasks)} tasks')

# Over-filled (> 5)
over = {k: v for k, v in cells.items() if len(v) > 5}
if over:
    log(f'\nOVER-FILLED CELLS ({len(over)}):')
    for ck, tasks in sorted(over.items()):
        log(f'  {ck}: {len(tasks)} tasks')

# Grade+Level summary (ignoring theme/subtopic)
gl_cells = Counter(f'G{t.get("grade","?")}|L{t.get("level","?")}' for t in l13)
log(f'\nGrade+Level distribution:')
for k, cnt in sorted(gl_cells.items()):
    log(f'  {k}: {cnt} tasks')

# ===== QUALITY METRICS =====
log(f'\n=== QUALITY METRICS ===')
for field in ['statement', 'answer', 'solution']:
    missing = sum(1 for t in l13 if not t.get(field))
    log(f'Missing "{field}": {missing}')

qs = [t.get('quality_score', 0) or 0 for t in l13]
if qs:
    log(f'Quality scores: min={min(qs):.0f}, max={max(qs):.0f}, avg={sum(qs)/len(qs):.1f}')
    q_dist = Counter()
    for q in qs:
        bucket = (q // 10) * 10
        q_dist[bucket] += 1
    log(f'Quality distribution: {dict(sorted(q_dist.items()))}')

fixed = sum(1 for t in l13 if t.get('fixed_by_ai'))
log(f'Fixed by AI: {fixed}')

statuses = Counter(str(t.get('decision_status', '?')) for t in l13)
log(f'Decision statuses: {dict(statuses)}')

fcs = Counter(str(t.get('final_court_status', '?')) for t in l13)
log(f'Final court statuses: {dict(fcs)}')

# ===== TOPICS =====
log(f'\n=== TOPIC COVERAGE ===')
themes = Counter(str(t.get('topic', '?')) for t in l13)
log(f'Unique topics: {len(themes)}')
log(f'Top 15 topics:')
for topic, cnt in themes.most_common(15):
    log(f'  {topic}: {cnt}')

# ===== SOURCES =====
log(f'\n=== SOURCE ANALYSIS ===')
sources = Counter(str(t.get('source', '?')) for t in l13)
log(f'Sources: {dict(sources)}')

evidence = Counter(str(t.get('evidence_source', '?')) for t in l13)
log(f'Evidence sources: {dict(evidence)}')

# ===== LOW QUALITY =====
low_q = [t for t in l13 if (t.get('quality_score') or 0) < 60]
log(f'\nLow quality tasks (<60): {len(low_q)}')
if low_q:
    log(f'By level: {dict(sorted(Counter(t["level"] for t in low_q).items()))}')

# ===== SUMMARY =====
log('\n\n========== SUMMARY ==========')
log(f'Total curated bank: {len(bank)} tasks')
log(f'L1-L3 (level field): {len(l13)} tasks')
log(f'L1-L3 (target_level): {len(l13_target)} tasks')
log(f'Level=None tasks: {len(none_level)}')
log(f'  - Could be L1-L3 (target_level): {sum(1 for t in none_level if t.get("target_level") in ("L1","L2","L3"))}')
log(f'Unique L1-L3 cells: {len(cells)}')
log(f'Under-filled cells (<5): {len(under)}')
log(f'Over-filled cells (>5): {len(over)}')
log(f'Missing statement: {sum(1 for t in l13 if not t.get("statement"))}')
log(f'Missing answer: {sum(1 for t in l13 if not t.get("answer"))}')
log(f'Missing solution: {sum(1 for t in l13 if not t.get("solution"))}')
log(f'Low quality (<60): {len(low_q)}')
log(f'Avg quality score: {sum(qs)/len(qs):.1f}' if qs else 'N/A')
