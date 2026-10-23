#!/usr/bin/env python3
"""Analyze current L3 cell state and available formyla candidates."""
import json, sys
from collections import defaultdict, Counter

sys.stdout = open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)

DOWN = r'C:\Users\Victor\Downloads'

with open(f'{DOWN}/final_clean_dataset_5levels.json', 'r', encoding='utf-8') as f:
    main = json.load(f)

# Count L3 tasks per cell
cell_counts = defaultdict(int)
cell_ids = defaultdict(list)
for t in main:
    if t.get('difficulty') == 3:
        key = (t['grade'], t['method_code'])
        cell_counts[key] += 1
        cell_ids[key].append(t['id'])

print("ALL L3 CELL COUNTS:")
print(f"{'Grade':>5} {'Method':>6} {'Count':>5}")
print("-" * 20)
incomplete = []
for key in sorted(cell_counts):
    g, m = key
    cnt = cell_counts[key]
    marker = ""
    if cnt < 5:
        marker = " <-- NEEDS FILLING"
        incomplete.append((g, m, cnt, 5 - cnt))
    print(f"  {g:>3}   {m:>4}   {cnt:>3}{marker}")

print(f"\n\nINCOMPLETE CELLS ({len(incomplete)} total):")
total_missing = 0
for g, m, have, need in incomplete:
    total_missing += need
    print(f"  Grade {g}, Method {m}: have {have}, need {need} more (target=5)")

print(f"\nTotal missing L3 tasks: {total_missing}")

# Now check formyla availability per cell
print("\n\nFORMYLA CANDIDATES FOR MISSING CELLS:")
with open(f'{DOWN}/formyla_dataset_slightly_fixed.json', 'r', encoding='utf-8') as f:
    formyla = json.load(f)

for g, m, have, need in incomplete:
    # Find formyla tasks at difficulty=3 matching this (grade, method)
    candidates = [t for t in formyla if t['grade'] == g and t['method_code'] == m and t.get('difficulty') == 3]
    all_diffs = Counter(t['difficulty'] for t in formyla if t['grade'] == g and t['method_code'] == m)
    print(f"\n  Grade {g}, Method {m} (need {need}):")
    print(f"    Formyla diff=3 candidates: {len(candidates)}")
    if candidates:
        # Show best ones
        good = [t for t in candidates if t.get('solution') and len(t.get('task_text','')) > 20]
        print(f"    With solution + text: {len(good)}")
        if good:
            for t in good[:3]:
                print(f"      id={t['id']}, text[:60]={t['task_text'][:60]}")
    else:
        print(f"    All difficulty dist: {dict(sorted(all_diffs.items()))}")
        print(f"    ** NO FORMULA CANDIDATES ** - need olympiad DB")

# Check olympiad DB for grade 5 problems
print("\n\nOLYMPIAD DB - Grade 5 problems:")
with open(f'{DOWN}/olympiad_DB_final_fixed.jsonl', 'r', encoding='utf-8') as f:
    oly_lines = [json.loads(l) for l in f if l.strip()]

grade5_entries = [e for e in oly_lines if e.get('grade') == 5]
print(f"  Total grade 5 entries: {len(grade5_entries)}")
for entry in grade5_entries[:5]:
    probs = entry.get('problems', [])
    print(f"  {entry.get('olympiad')} {entry.get('year')} round={entry.get('round')}: {len(probs)} problems")
    for p in probs[:2]:
        text = p.get('text', '')[:80]
        has_sol = bool(p.get('solution'))
        has_ans = bool(p.get('answer'))
        print(f"    P{p.get('num')}: text='{text}...' solution={'Y' if has_sol else 'N'} answer={'Y' if has_ans else 'N'}")
