#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Analyze cell coverage for Level 1 and Level 2.
A cell = (level, grade, subtopic) with target = 5 tasks.
A "дыра" (hole) = cell with < 5 tasks.
"""
import json
from collections import Counter, defaultdict

with open('adaptive_data/adaptive_full_9120_fixed.json', 'r', encoding='utf-8') as f:
    db = json.load(f)

print(f"Total tasks in DB: {len(db)}")

# Examine first few tasks for structure
for i in range(min(3, len(db))):
    t = db[i]
    print(f"\n--- Task {i} ---")
    for k, v in t.items():
        if isinstance(v, str) and len(v) > 120:
            print(f"  {k}: {v[:120]}...")
        else:
            print(f"  {k}: {v}")

# Check what field we use for subtopic
# Try: subtopic, topic, sub_topic, subcategory
possible_subtopic_keys = ['subtopic', 'sub_topic', 'subcategory', 'sub_category', 'subtopic_id', 'subtopic_name']
for k in possible_subtopic_keys:
    count = sum(1 for t in db if k in t)
    print(f"\nField '{k}' present in {count}/{len(db)} tasks")

# Also check topic field
print(f"\nTopic field samples:")
topics = set()
for t in db:
    topic = t.get('topic', '')
    if topic:
        topics.add(topic)
print(f"Unique topics: {len(topics)}")
if topics:
    print(f"Sample topics: {sorted(list(topics))[:10]}")

# Check grade values
grades = set()
for t in db:
    g = t.get('grade')
    if g is not None:
        grades.add(g)
print(f"\nUnique grades: {sorted(grades)}")
