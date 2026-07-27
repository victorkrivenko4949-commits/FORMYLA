#!/usr/bin/env python3
"""Comprehensive diagnostic for Phase 5 - understanding all data sources."""
import json, sys
from collections import Counter

sys.stdout = open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)

DOWN = r'C:\Users\Victor\Downloads'

# ============================================================
# 1. FORMULA DATASET - structure and content
# ============================================================
with open(f'{DOWN}/formyla_dataset_slightly_fixed.json', 'r', encoding='utf-8') as f:
    formyla = json.load(f)

print("=" * 70)
print("FORMYLA DATASET")
print("=" * 70)
print(f"Total tasks: {len(formyla)}")
print(f"Keys of first task: {list(formyla[0].keys())}")
# Show a complete sample task (truncated text)
t = formyla[0]
for k, v in t.items():
    val = str(v)
    if len(val) > 120:
        val = val[:120] + "..."
    print(f"  {k}: {val}")

# Check what themes map to what methods for our incomplete cells
from collections import defaultdict
print("\n\nTHEME-TO-METHOD mapping for FORMULA dataset:")
theme_methods = defaultdict(set)
for t in formyla:
    theme_methods[t.get('theme', '?')].add(t['method_code'])
for theme in sorted(theme_methods):
    print(f"  Theme '{theme}': methods = {sorted(theme_methods[theme])}")

# ============================================================
# 2. Check method codes F3, G1, G2 in methods catalog 105
# ============================================================
with open('data/olympiads/methods_catalog_105.json', 'r', encoding='utf-8') as f:
    catalog = json.load(f)

print("\n\nMETHODS CATALOG: F3, G1, G2")
for entry in catalog:
    if entry['method_code'] in ('F3', 'G1', 'G2'):
        print(f"  {entry['method_code']}: {entry['method_name']}, section={entry['section']}, grades={entry['grades']}")

# ============================================================
# 3. VSOSH Grade 9 - complete structure
# ============================================================
with open(f'{DOWN}/vsosh_9_2027_tasks_v3.json', 'r', encoding='utf-8') as f:
    vsosh9 = json.load(f)

print("\n\nVSOSH GRADE 9")
print("=" * 70)
print(f"Total tasks: {len(vsosh9)}")
print(f"Keys of first task: {list(vsosh9[0].keys())}")
t = vsosh9[0]
for k, v in t.items():
    val = str(v)
    if len(val) > 150:
        val = val[:150] + "..."
    print(f"  {k}: {val}")

# F3 tasks in vsosh9
print("\nF3 tasks in vsosh9:")
f3_tasks = [t for t in vsosh9 if t['method_primary'] == 'F3']
print(f"  Count: {len(f3_tasks)}")
for t in f3_tasks[:3]:
    print(f"  id={t.get('id','?')}, difficulty={t.get('difficulty')}, condition[:80]={t.get('condition_md','')[:80]}")

# ============================================================
# 4. VSOSH Grades 10-11
# ============================================================
with open(f'{DOWN}/vsosh_zadachi_10_11_2027.json', 'r', encoding='utf-8') as f:
    vsosh10 = json.load(f)

tasks10 = vsosh10.get('tasks', []) if isinstance(vsosh10, dict) else vsosh10
print("\n\nVSOSH 10-11")
print("=" * 70)
print(f"Total tasks: {len(tasks10)}")
if tasks10:
    print(f"Keys of first task: {list(tasks10[0].keys())}")
    t = tasks10[0]
    for k, v in t.items():
        val = str(v)
        if len(val) > 150:
            val = val[:150] + "..."
        print(f"  {k}: {val}")

# ============================================================
# 5. OLYMPIAD DB - structure and content
# ============================================================
with open(f'{DOWN}/olympiad_DB_final_fixed.jsonl', 'r', encoding='utf-8') as f:
    oly_lines = [json.loads(l) for l in f if l.strip()]

print("\n\nOLYMPIAD DB")
print("=" * 70)
print(f"Total entries: {len(oly_lines)}")
print(f"Keys of first entry: {list(oly_lines[0].keys())}")
entry = oly_lines[0]
for k, v in entry.items():
    val = str(v)
    if len(val) > 150:
        val = val[:150] + "..."
    print(f"  {k}: {val}")

# Look at problems structure
print("\nSample problem entry:")
for i, entry in enumerate(oly_lines[:50]):
    probs = entry.get('problems', [])
    if probs:
        p = probs[0]
        p_keys = list(p.keys())
        print(f"  Entry {i}: olympiad={entry.get('olympiad')}, year={entry.get('year')}, grade={entry.get('grade')}, round={entry.get('round')}")
        print(f"    Problem keys: {p_keys}")
        for k in p_keys:
            val = str(p[k])
            if len(val) > 100:
                val = val[:100] + "..."
            print(f"    {k}: {val}")
        break

# Count olympiads and grades
olympiads = Counter()
grades_present = Counter()
for entry in oly_lines:
    olympiads[entry.get('olympiad', '?')] += 1
    grades_present[entry.get('grade', '?')] += 1

print(f"\nOlympiads: {dict(olympiads.most_common(20))}")
print(f"Grades: {dict(sorted(grades_present.items()))}")

# ============================================================
# 6. Current incomplete cells - what's needed
# ============================================================
with open(f'{DOWN}/final_clean_dataset_5levels.json', 'r', encoding='utf-8') as f:
    out_main = json.load(f)

print("\n\nCURRENT STATE - INCOMPLETE CELLS")
print("=" * 70)
CELLS = [(5,'F3',4),(5,'G2',4),(6,'B1',4),(6,'D2',4),(6,'G1',1),(6,'G2',2),
         (7,'B1',4),(7,'G2',1),(8,'A3',4),(8,'B1',2),(8,'B2',4),(8,'B3',4),
         (8,'D2',4),(10,'B2',4),(10,'D2',4),(10,'G2',3)]

for g, m, need in CELLS:
    l3 = [t for t in out_main if t['grade']==g and t['method_code']==m and t['difficulty']==3]
    have = len(l3)
    missing = need - have
    if have < need:
        print(f"  Grade {g}, Method {m}: have {have}, need {need}, missing {missing}")
        if l3:
            print(f"    Existing IDs: {[t['id'] for t in l3]}")

# Check max ID to determine new ID format
ids = [t['id'] for t in out_main]
print(f"\nMax existing ID: {max(ids)}")
print(f"Last 10 IDs: {sorted(ids)[-10:]}")
print(f"ID prefixes: {Counter(i.split('-')[0] for i in ids).most_common(30)}")
