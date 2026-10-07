#!/usr/bin/env python3
"""Показать Grade|Level|Topic матрицу для L1-L3 задач (subtopic везде None)."""
import json
import sys
from collections import defaultdict

bank = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))

TARGET_GRADES = {2, 5, 6, 7, 8, 9, 10, 11}
TARGET_LEVELS = {1, 2, 3}

# Grade|Level -> {topic -> count}
gl_topics = defaultdict(lambda: defaultdict(int))
gl_total = defaultdict(int)

for t in bank:
    g = t.get("grade")
    lv = t.get("level")
    if g is None or lv is None:
        continue
    g, lv = int(g), int(lv)
    if g not in TARGET_GRADES or lv not in TARGET_LEVELS:
        continue
    topic = t.get("topic", "").strip()
    if not topic:
        topic = "(no topic)"
    key = (g, lv)
    gl_topics[key][topic] += 1
    gl_total[key] += 1

sorted_grades = sorted(TARGET_GRADES)
sorted_levels = sorted(TARGET_LEVELS)

# Print matrix header
print("=" * 60)
print("MATRIX: Grade|Level -> Topics (with task counts)")
print("=" * 60)
print()

all_topics_set = set()
for (g, lv), topics in sorted(gl_topics.items()):
    for topic in topics:
        all_topics_set.add(topic)
all_topics_sorted = sorted(all_topics_set)

# Print per cell
occupied = 0
missing = 0
for g in sorted_grades:
    for lv in sorted_levels:
        key = (g, lv)
        if key in gl_topics:
            occupied += 1
            topics = gl_topics[key]
            total = gl_total[key]
            print(f"[G{g}|L{lv}]  TOTAL={total:2d}  topics={len(topics)}")
            for topic, cnt in sorted(topics.items(), key=lambda x: -x[1]):
                print(f"         - {topic}: {cnt}")
            print()
        else:
            missing += 1
            print(f"[G{g}|L{lv}]  *** MISSING *** (0 tasks)")
            print()

print("=" * 60)
print(f"Occupied Grade|Level cells: {occupied}/24")
print(f"Missing Grade|Level cells:  {missing}/24")
print(f"Total unique topics across all L1-L3: {len(all_topics_sorted)}")
print(f"Total L1-L3 tasks: {sum(gl_total.values())}")
print("=" * 60)

# Print summary table
print()
print("SUMMARY TABLE (Grade x Level -> task count)")
print()
header = "Grade    "
for lv in sorted_levels:
    header += f"| L{lv}  "
print(header)
print("-" * len(header))
for g in sorted_grades:
    row = f"G{g:<5d}  "
    for lv in sorted_levels:
        cnt = gl_total.get((g, lv), 0)
        row += f"| {cnt:>3d} "
    print(row)
print("-" * len(header))
total_row = "Total    "
for lv in sorted_levels:
    tot = sum(gl_total.get((g, lv), 0) for g in sorted_grades)
    total_row += f"| {tot:>3d} "
print(total_row)
