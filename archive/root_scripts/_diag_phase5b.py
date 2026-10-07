#!/usr/bin/env python3
"""Deep dive into available olympiad data for Phase 5 filling."""
import json, sys
from collections import Counter, defaultdict

sys.stdout = open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)

DOWN = r'C:\Users\Victor\Downloads'

# The 16 incomplete cells with their themes
INCOMPLETE = {
    (5, 'F3'): 4,  (5, 'G2'): 4,
    (6, 'B1'): 4,  (6, 'D2'): 4,  (6, 'G1'): 1,  (6, 'G2'): 2,
    (7, 'B1'): 4,  (7, 'G2'): 1,
    (8, 'A3'): 4,  (8, 'B1'): 2,  (8, 'B2'): 4,  (8, 'B3'): 4,  (8, 'D2'): 4,
    (10, 'B2'): 4, (10, 'D2'): 4, (10, 'G2'): 3,
}

print("=" * 60)
print("1. FORMULA DATASET ANALYSIS")
print("=" * 60)

with open(f'{DOWN}/formyla_dataset_slightly_fixed.json', 'r', encoding='utf-8') as f:
    formyla = json.load(f)

print(f"Total formyla tasks: {len(formyla)}")

# Check difficulty range
diffs = Counter(t['difficulty'] for t in formyla)
print(f"Difficulty distribution: {dict(sorted(diffs.items()))}")

# Check if any tasks match our incomplete cells
for (g, m), need in sorted(INCOMPLETE.items()):
    matches = [t for t in formyla if t['grade'] == g and t['method_code'] == m]
    print(f"\nGrade={g}, Method={m} (need {need}): {len(matches)} formyla tasks")
    if matches:
        # Show difficulty distribution
        md = Counter(t['difficulty'] for t in matches)
        print(f"  Difficulty dist: {dict(sorted(md.items()))}")
        for t in matches[:3]:
            print(f"  id={t['id']}, diff={t['difficulty']}")
            print(f"  theme={t.get('theme')}, subtopic={t.get('subtopic')}")

print("\n" + "=" * 60)
print("2. VSOSH GRADE 9 TASKS")
print("=" * 60)

with open(f'{DOWN}/vsosh_9_2027_tasks_v3.json', 'r', encoding='utf-8') as f:
    vsosh9 = json.load(f)

print(f"Total vsosh grade 9 tasks: {len(vsosh9)}")

# Method distribution
methods = Counter(t['method_primary'] for t in vsosh9)
print(f"Method distribution: {dict(sorted(methods.items()))}")

# Check which methods match our incomplete cells
for (g, m), need in sorted(INCOMPLETE.items()):
    if g == 9:  # Grade 9
        matches = [t for t in vsosh9 if t['method_primary'] == m]
        print(f"  Need Grade=9, Method={m} (need {need}): {len(matches)} vsosh tasks")
    elif g == 8 or g == 10:  # Close grades
        matches = [t for t in vsosh9 if t['method_primary'] == m]
        if matches:
            print(f"  Close: Grade={g}, Method={m} (need {need}): {len(matches)} vsosh-9 tasks (may adapt)")

# Sample a task with solution
print("\nSample vsosh task with full fields:")
for t in vsosh9:
    if t.get('solution_md') and len(t['solution_md']) > 50:
        print(f"  method={t['method_primary']}, difficulty={t['difficulty']}")
        print(f"  condition[:80]={t['condition_md'][:80]}")
        print(f"  solution[:80]={t['solution_md'][:80]}")
        print(f"  answer={t.get('answer','')[:50]}")
        break

print("\n" + "=" * 60)
print("3. VSOSH GRADES 10-11 TASKS")
print("=" * 60)

with open(f'{DOWN}/vsosh_zadachi_10_11_2027.json', 'r', encoding='utf-8') as f:
    vsosh10 = json.load(f)

tasks = vsosh10.get('tasks', [])
print(f"Total vsosh 10-11 tasks: {len(tasks)}")
if tasks:
    print(f"Sample task keys: {list(tasks[0].keys()) if isinstance(tasks[0], dict) else 'N/A'}")
    if isinstance(tasks[0], dict):
        for k, v in tasks[0].items():
            print(f"  {k}: {str(v)[:80]}")

# Method distribution
if tasks and isinstance(tasks[0], dict):
    methods10 = Counter(t.get('method_primary', 'N/A') for t in tasks)
    print(f"\nMethod distribution: {dict(sorted(methods10.items()))}")
    
    # Check which methods match our incomplete cells for grades 10
    for (g, m), need in sorted(INCOMPLETE.items()):
        if g == 10:
            matches = [t for t in tasks if t.get('method_primary') == m]
            print(f"  Need Grade=10, Method={m} (need {need}): {len(matches)} vsosh-10 tasks")

print("\n" + "=" * 60)
print("4. OLYMPIAD DB - PROBLEMS ANALYSIS")
print("=" * 60)

with open(f'{DOWN}/olympiad_DB_final_fixed.jsonl', 'r', encoding='utf-8') as f:
    lines = [json.loads(l) for l in f if l.strip()]

print(f"Total olympiad entries: {len(lines)}")

# Grade distribution
grades = Counter()
for entry in lines:
    g = entry.get('grade', '?')
    grades[g] += 1
print(f"Grade distribution: {dict(sorted(grades.items()))}")

# Check for problems that could match our method codes
# The olympiad DB has problems[{'num': int, 'text': str, 'solution': str?, 'answer': str?}]
# It doesn't have method_code, so we'd need to find relevant problems by theme

# Show a sample problem with solution
for entry in lines:
    probs = entry.get('problems', [])
    if probs and len(probs) > 0:
        p = probs[0]
        if p.get('solution') and len(p.get('solution', '')) > 30:
            print(f"\nSample olympiad entry:")
            print(f"  olympiad={entry.get('olympiad')}, year={entry.get('year')}, grade={entry.get('grade')}")
            print(f"  round={entry.get('round')}")
            print(f"  problem text[:80]={p.get('text','')[:80]}")
            print(f"  has solution: {bool(p.get('solution'))}")
            print(f"  has answer: {bool(p.get('answer'))}")
            break

print("\n" + "=" * 60)
print("5. MAX ID AND NEW ID PREFIX")
print("=" * 60)

with open(f'{DOWN}/final_clean_dataset_5levels.json', 'r', encoding='utf-8') as f:
    out_main = json.load(f)

ids = [t['id'] for t in out_main]
print(f"Max ID: {max(ids)}")
print(f"Sample IDs (last 10): {sorted(ids)[-10:]}")
print(f"ID prefixes used: {Counter(i.split('-')[0] for i in ids).most_common(20)}")
