#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create generation plan for grade 8 adaptive test."""
import json, os

AUDIT_FILE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'data', 'audit', 'grade8_audit.json')
PLAN_FILE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'data', 'audit', 'grade8_gen_plan.json')

audit = json.load(open(AUDIT_FILE, encoding='utf-8'))

# Get unique topics
topics = sorted(set(r['topic'] for r in audit))
print(f'Grade 8 topics ({len(topics)}):')
for t in topics:
    counts = {r['level']: r['count'] for r in audit if r['topic'] == t}
    total = sum(counts.values())
    print(f'  {t}: {total} tasks, levels: {counts}')

# Target: ~1050 tasks, 15 topics => ~70 per topic
# Each topic needs L1-L5 (14 per level per topic)
TARGET_PER_LEVEL = 14
plan = []
for t in topics:
    counts = {r['level']: r['count'] for r in audit if r['topic'] == t}
    for lvl in range(1, 6):
        have = counts.get(lvl, 0)
        gen = max(0, TARGET_PER_LEVEL - have)
        if gen > 0:
            plan.append({'topic': t, 'difficulty': lvl, 'count': gen, 'priority': 1})

total_plan = sum(p['count'] for p in plan)
print(f'\nGeneration plan: {len(plan)} items, {total_plan} tasks')
json.dump(plan, open(PLAN_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'Saved to {PLAN_FILE}')
