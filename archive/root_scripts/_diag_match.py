#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnose matching between tasks_solutions_out.json keys and olympiads.py records."""
import json, sys, os

os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

# Load olympiads.py
with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()
exec(content)
db = OLYMPIADS_DB  # type: ignore

# Build lookup: (olympiad, year, grade, round) -> list of records
lookup = {}
for rec in db:
    key = (rec['olympiad'], rec['year'], rec['grade'], rec['round'])
    lookup.setdefault(key, []).append(rec)

print(f"Total olympiad records: {len(db)}")
print(f"Unique (olympiad, year, grade, round) combos: {len(lookup)}")

# Show sample rounds
rounds = set()
for rec in db:
    rounds.add(rec['round'])
print(f"\nUnique round values ({len(rounds)}):")
for r in sorted(rounds)[:20]:
    cnt = sum(1 for rec in db if rec['round'] == r)
    print(f"  '{r}' -> {cnt} records")

# Load solutions
sol_path = r'C:\Users\Victor\Downloads\tasks_solutions_out.json'
with open(sol_path, 'r', encoding='utf-8') as f:
    solutions = json.load(f)
print(f"\nTotal solutions: {len(solutions)}")

# Try matching each solution
matched = 0
unmatched = []
for s in solutions:
    k = (s['olympiad'], s['year'], s['grade'], s['round'])
    candidates = lookup.get(k, [])
    # Find matching problem num
    found = False
    for rec in candidates:
        for p in rec['problems']:
            if str(p['num']) == str(s['num']):
                found = True
                break
        if found:
            break
    if found:
        matched += 1
    else:
        unmatched.append((s['key'], k, [r['olympiad'] for r in candidates]))

print(f"Matched: {matched}/{len(solutions)}")
if unmatched:
    print(f"\nUnmatched ({len(unmatched)}):")
    for key, k, cands in unmatched[:5]:
        print(f"  key={key}")
        print(f"    lookup key: {k}")
        print(f"    candidates in DB for olympiad: {cands}")
