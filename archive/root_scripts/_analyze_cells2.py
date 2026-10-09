#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Analyze cell coverage for Level 1 and Level 2.
A cell = (level, grade, topic/section) with target = 5 tasks per cell.
"дыра" = cell with < 5 tasks.
"""
import json
from collections import Counter, defaultdict

with open('adaptive_data/adaptive_full_9120_fixed.json', 'r', encoding='utf-8') as f:
    db = json.load(f)

print(f"Total tasks in DB: {len(db)}")

# Filter L1 and L2
l1 = [t for t in db if t.get('level') == 1]
l2 = [t for t in db if t.get('level') == 2]
print(f"\nL1 count: {len(l1)}")
print(f"L2 count: {len(l2)}")

# Check section field
print(f"\n--- SECTION field ---")
sections_l1 = set(t.get('section','') for t in l1)
sections_l2 = set(t.get('section','') for t in l2)
print(f"L1 unique sections: {len(sections_l1)}")
print(f"L2 unique sections: {len(sections_l2)}")
if sections_l1:
    print(f"L1 sample sections: {sorted(sections_l1)[:10]}")
if sections_l2:
    print(f"L2 sample sections: {sorted(sections_l2)[:10]}")

# Check topic field
print(f"\n--- TOPIC field ---")
topics_l1 = set(t.get('topic','') for t in l1)
topics_l2 = set(t.get('topic','') for t in l2)
print(f"L1 unique topics: {len(topics_l1)}")
print(f"L2 unique topics: {len(topics_l2)}")

# Check grade field
grades_l1 = sorted(set(t.get('grade') for t in l1))
grades_l2 = sorted(set(t.get('grade') for t in l2), key=lambda x: str(x))
print(f"\nL1 grades: {grades_l1}")
print(f"L2 grades: {grades_l2}")

# Group by (level, grade, topic) and count
print(f"\n=== CELL ANALYSIS (level, grade, topic) ===")
for level_name, tasks in [("L1", l1), ("L2", l2)]:
    cells = defaultdict(list)
    for t in tasks:
        key = (t.get('grade'), t.get('topic', ''))
        cells[key].append(t)
    
    holes = {k: v for k, v in cells.items() if len(v) < 5}
    full = {k: v for k, v in cells.items() if len(v) == 5}
    over = {k: v for k, v in cells.items() if len(v) > 5}
    
    print(f"\n{level_name}:")
    print(f"  Total cells (grade, topic): {len(cells)}")
    print(f"  Full cells (==5): {len(full)}")
    print(f"  Overfilled cells (>5): {len(over)}")
    print(f"  HOLES (<5): {len(holes)}")
    
    if holes:
        print(f"  Hole details (sorted by count asc):")
        for key in sorted(holes.keys(), key=lambda k: len(holes[k])):
            grade, topic = key
            count = len(holes[key])
            print(f"    grade={grade}, topic='{topic}' -> {count}/5 tasks")
    
    if over:
        print(f"  Overfilled examples:")
        over_sorted = sorted(over.items(), key=lambda x: -len(x[1]))[:5]
        for key, tasks_list in over_sorted:
            grade, topic = key
            print(f"    grade={grade}, topic='{topic}' -> {len(tasks_list)} tasks")

# Also check by (level, grade, section)
print(f"\n=== CELL ANALYSIS (level, grade, section) ===")
for level_name, tasks in [("L1", l1), ("L2", l2)]:
    cells = defaultdict(list)
    for t in tasks:
        key = (t.get('grade'), t.get('section', ''))
        cells[key].append(t)
    
    holes = {k: v for k, v in cells.items() if len(v) < 5}
    full = {k: v for k, v in cells.items() if len(v) == 5}
    
    print(f"\n{level_name}:")
    print(f"  Total cells (grade, section): {len(cells)}")
    print(f"  Full cells (==5): {len(full)}")
    print(f"  HOLES (<5): {len(holes)}")
    
    if holes:
        print(f"  Holes (sorted by count asc):")
        for key in sorted(holes.keys(), key=lambda k: len(holes[k])):
            grade, section = key
            count = len(holes[key])
            print(f"    grade={grade}, section='{section}' -> {count}/5 tasks")
