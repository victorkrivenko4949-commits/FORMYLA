#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostic script for olympiads.py - outputs to file to avoid encoding issues."""
import sys
import json
from collections import defaultdict

# Write output to a file to avoid terminal encoding issues
out_path = "_diag_olympiads_report.txt"
sys.stdout = open(out_path, "w", encoding="utf-8")

from olympiads import OLYMPIADS_DB

print(f"Total olympiads: {len(OLYMPIADS_DB)}")
print()

# ===== 1. Find tasks where 'text' contains solution keywords =====
solution_keywords = ['Решение:', 'Ответ:', 'Решение.=', 'Ответ.=']
bad_tasks = []
for o in OLYMPIADS_DB:
    for p in o.get('problems', []):
        t = p.get('text', '')
        for kw in solution_keywords:
            if kw in t:
                bad_tasks.append({
                    'id': o['id'],
                    'olympiad': o['olympiad'],
                    'olympiad_title': o['olympiad_title'],
                    'year': o['year'],
                    'grade': o['grade'],
                    'round': o.get('round',''),
                    'round_title': o.get('round_title',''),
                    'problem_num': p['num'],
                    'text_preview': t[:200],
                    'solution_preview': p.get('solution','')[:100]
                })
                break

print("=" * 70)
print(f"TASKS WHERE CONDITION CONTAINS SOLUTION: {len(bad_tasks)}")
print("=" * 70)
for bt in bad_tasks:
    print(f"\n  [{bt['id']}] {bt['olympiad_title']} {bt['year']} g{bt['grade']}")
    print(f"    Round: {bt['round']} / {bt['round_title']}")
    print(f"    Problem #{bt['problem_num']}")
    print(f"    TEXT: {bt['text_preview']}")
    print(f"    SOLUTION: {bt['solution_preview']}")

print()
print("=" * 70)
print("UNIQUE ROUND VALUES")
print("=" * 70)
rounds = set()
for o in OLYMPIADS_DB:
    rounds.add((o.get('round',''), o.get('round_title','')))
for r, rt in sorted(rounds):
    count = sum(1 for o in OLYMPIADS_DB if o.get('round')==r and o.get('round_title')==rt)
    print(f"  round={r!r:30s}  round_title={rt!r:40s}  count={count}")

print()
print("=" * 70)
print("OLYMPIADS WITH MULTIPLE ROUND ENTRIES (potential two-day events)")
print("=" * 70)
by_key = defaultdict(list)
for o in OLYMPIADS_DB:
    key = (o['olympiad'], o['year'], o['grade'])
    by_key[key].append(o)

multi_round = {k: v for k, v in by_key.items() if len(v) > 1}
print(f"Count: {len(multi_round)}")
for key in sorted(multi_round.keys())[:30]:
    entries = multi_round[key]
    rounds_str = ' | '.join(f"{e.get('round','?')}/{e.get('round_title','?')}" for e in entries)
    prob_counts = ' | '.join(f"{len(e.get('problems',[]))} задач" for e in entries)
    ids = ' | '.join(str(e['id']) for e in entries)
    print(f"\n  {key[0]} {key[1]} g{key[2]}")
    print(f"    ids={ids}")
    print(f"    rounds: {rounds_str}")
    print(f"    problems: {prob_counts}")

# ===== 3. Check 'round' values for day indicators =====
print()
print("=" * 70)
print("ROUND VALUES THAT MENTION DAY/DEN")
print("=" * 70)
for r, rt in sorted(rounds):
    if 'день' in r.lower() or 'день' in rt.lower() or 'day' in r.lower():
        count = sum(1 for o in OLYMPIADS_DB if o.get('round')==r and o.get('round_title')==rt)
        print(f"  round={r!r:30s}  round_title={rt!r:40s}  count={count}")

sys.stdout.close()
print(f"\nReport written to {out_path}")
