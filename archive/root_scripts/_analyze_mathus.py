#!/usr/bin/env python3
"""Analyze mathus_olympiads.json vs olympiads.py data."""
import json, ast, sys

# Load mathus data
with open('data/mathus_olympiads.json', 'r', encoding='utf-8') as f:
    mathus = json.load(f)

# Load olympiads.py
with open('olympiads.py', 'r', encoding='utf-8') as f:
    src = f.read()
tree = ast.parse(src)
olymp = None
for n in ast.walk(tree):
    if isinstance(n, ast.Assign):
        for t in n.targets:
            if isinstance(t, ast.Name) and t.id == 'OLYMPIADS_DB':
                olymp = ast.literal_eval(n.value)

print(f"olympiads.py: {len(olymp)} records")
print(f"mathus_olympiads.json: {len(mathus)} records")

from collections import Counter
oc = Counter(i['olympiad'] for i in olymp)
mc = Counter(i['olympiad'] for i in mathus)
print("\n=== olympiads.py by olympiad ===")
for k, v in sorted(oc.items()):
    print(f"  {k}: {v}")
print("\n=== mathus_olympiads.json by olympiad ===")
for k, v in sorted(mc.items()):
    print(f"  {k}: {v}")

# Shared olympiads
shared = set(oc.keys()) & set(mc.keys())
print(f"\n=== Shared olympiads: {shared} ===")

# For phystech, do detailed comparison
print("\n\n========== DETAILED PHYSTECH COMPARISON ==========")

mathus_ph = [i for i in mathus if i['olympiad'] == 'phystech']
olymp_ph = [i for i in olymp if i['olympiad'] == 'phystech']

print(f"\nolympiads.py phystech: {len(olymp_ph)} records")
for i in olymp_ph:
    probs = i.get('problems', [])
    print(f"  id={i['id']}, year={i['year']}, grade={i['grade']}, round={i['round']}, title={i.get('round_title','?')}, problems={len(probs)}")

print(f"\nmathus_olympiads.json phystech: {len(mathus_ph)} records")
for i in mathus_ph:
    probs = i.get('problems', [])
    print(f"  id={i['id']}, year={i['year']}, grade={i['grade']}, round={i['round']}, title={i['round_title']}, problems={len(probs)}")

# Check for matching records
print("\n\n=== Attempting to match by (year, grade, round) ===")
# Normalize year to string for comparison
olymp_by_key = {}
for i in olymp_ph:
    key = (str(i['year']), str(i['grade']), i['round'])
    olymp_by_key[key] = i

matched = 0
unmatched_mathus = []
for i in mathus_ph:
    key = (str(i['year']), str(i['grade']), i['round'])
    if key in olymp_by_key:
        matched += 1
        o = olymp_by_key[key]
        # Compare problems
        m_probs = {(p['num'],) : p for p in i['problems']}
        o_probs = {(p['num'],) : p for p in o.get('problems', [])}
        same_nums = set(m_probs.keys()) & set(o_probs.keys())
        diff_answer = []
        diff_text = []
        diff_solution = []
        for nk in same_nums:
            mp = m_probs[nk]
            op = o_probs[nk]
            if mp.get('answer','') != op.get('answer',''):
                diff_answer.append((nk[0], mp.get('answer',''), op.get('answer','')))
            if len(mp.get('text','')) > 20 and len(op.get('text','')) > 20:
                # Compare first 100 chars
                if mp['text'][:100] != op['text'][:100]:
                    diff_text.append((nk[0], 'DIFFERENT'))
        if diff_answer:
            print(f"  MATCHED id={i['id']} year={i['year']} grade={i['grade']} round={i['round']}")
            print(f"    ANSWER DIFFS: {diff_answer}")
    else:
        unmatched_mathus.append(i)

print(f"\nMatched phystech records: {matched}/{len(mathus_ph)}")
print(f"Unmatched mathus records: {len(unmatched_mathus)}")
for i in unmatched_mathus[:10]:
    print(f"  id={i['id']} year={i['year']} grade={i['grade']} round={i['round']}")
