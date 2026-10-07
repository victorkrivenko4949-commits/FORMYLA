#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Analyze cell counts including subtopics from the curated bank.

The curated bank has grade (int), level (int), and topic (string) fields.
We need to figure out how the cells are structured with subtopics.
"""
import json
import os
from collections import defaultdict, Counter

BANK_PATH = 'curated_bank_L1_L5_fixed.json'

with open(BANK_PATH, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total tasks in bank: {len(data)}")

# First, find what fields exist and what types grade/level are
for i, t in enumerate(data[:3]):
    print(f"\nTask {i}:")
    print(f"  grade={repr(t.get('grade'))} type={type(t.get('grade')).__name__}")
    print(f"  level={repr(t.get('level'))} type={type(t.get('level')).__name__}")
    print(f"  topic={repr(t.get('topic', 'N/A'))}")
    print(f"  has subtopic: {'subtopic' in t}")
    print(f"  has theme: {'theme' in t}")

# For ALL tasks, check if any have subtopic or theme fields
has_subtopic = sum(1 for t in data if 'subtopic' in t and t['subtopic'])
has_theme = sum(1 for t in data if 'theme' in t and t['theme'])
has_topic = sum(1 for t in data if 'topic' in t and t['topic'])
print(f"\nTasks with subtopic field: {has_subtopic}")
print(f"Tasks with theme field: {has_theme}")
print(f"Tasks with topic field: {has_topic}")

# Check all unique topic values (non-empty, non-garbled)
topics = Counter()
for t in data:
    topic = t.get('topic', '')
    if topic and not any(ord(c) > 127 for c in str(topic)):
        topics[str(topic)] += 1
    elif topic:
        topics['[GARBLED]'] += 1

print(f"\nUnique topic values: {len(topics)}")
for topic, count in topics.most_common(20):
    print(f"  [{count:4d}] {topic[:80]}")

# TARGET MATRIX: grades G2(2), G5(5), G6(6), G7(7), G8(8), G9(9), G10(10), G11(11)
# Levels L1(1), L2(2), L3(3)
TARGET_GRADES = {2, 5, 6, 7, 8, 9, 10, 11}
TARGET_LEVELS = {1, 2, 3}

# Count by grade|level
gl_cells = defaultdict(int)
for t in data:
    g = t.get('grade')
    l = t.get('level')
    if g in TARGET_GRADES and l in TARGET_LEVELS:
        gl_cells[(g, l)] += 1

print(f"\n=== Grade|Level cells ({len(gl_cells)}) ===")
for gl in sorted(gl_cells.keys()):
    print(f"  G{gl[0]}|L{gl[1]}: {gl_cells[gl]} tasks")

# Count by grade|level|topic
glt_cells = defaultdict(int)
for t in data:
    g = t.get('grade')
    l = t.get('level')
    topic = t.get('topic', '')
    if g in TARGET_GRADES and l in TARGET_LEVELS:
        glt_cells[(g, l, topic)] += 1

print(f"\n=== Grade|Level|Topic cells ({len(glt_cells)}) ===")
for glt in sorted(glt_cells.keys()):
    g, l, topic = glt
    topic_short = topic[:50] if topic else '(empty)'
    print(f"  G{g}|L{l}|[{topic_short}]: {glt_cells[glt]} tasks")
