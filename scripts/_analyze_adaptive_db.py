#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analyze data/adaptive_full_db.json structure."""
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('data/adaptive_full_db.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total tasks: {len(data)}")
print(f"Keys: {list(data[0].keys())}")
print()

# By grade
grades = {}
for t in data:
    g = str(t.get('grade', '?'))
    grades[g] = grades.get(g, 0) + 1

print("=== BY GRADE ===")
for g in sorted(grades.keys(), key=lambda x: int(x) if x.isdigit() else 99):
    print(f"  Grade {g}: {grades[g]}")

# By topic
topics = {}
for t in data:
    tp = str(t.get('topic', 'no_topic'))
    topics[tp] = topics.get(tp, 0) + 1

print(f"\n=== BY TOPIC ({len(topics)} unique) ===")
for tp, c in sorted(topics.items(), key=lambda x: -x[1]):
    print(f"  {tp}: {c}")

# By grade+topic
print(f"\n=== BY GRADE+TOPIC ===")
grade_topics = {}
for t in data:
    g = str(t.get('grade', '?'))
    tp = str(t.get('topic', 'no_topic'))
    key = f"Grade {g}"
    if key not in grade_topics:
        grade_topics[key] = {}
    grade_topics[key][tp] = grade_topics[key].get(tp, 0) + 1

for g in sorted(grade_topics.keys(), key=lambda x: int(x.split()[-1]) if x.split()[-1].isdigit() else 99):
    total = sum(grade_topics[g].values())
    print(f"\n  {g} ({total} total):")
    for tp, c in sorted(grade_topics[g].items(), key=lambda x: -x[1]):
        print(f"    {tp}: {c}")

# Sample task
print(f"\n=== SAMPLE TASK ===")
s = data[0]
for k, v in s.items():
    print(f"  {k}: {str(v)[:100]}")
