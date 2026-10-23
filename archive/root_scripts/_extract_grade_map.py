#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json, sys

with open('curated_bank_L1_L5_taxonomy_v2.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

grade_topics = {}
topic_grades = {}

for item in data:
    if not isinstance(item, dict):
        continue
    g = item.get('class_level') or item.get('grade')
    t = item.get('topic', '')
    if g is None or not t:
        continue
    g = str(g).strip()
    t = t.strip()
    if g not in grade_topics:
        grade_topics[g] = set()
    grade_topics[g].add(t)
    if t not in topic_grades:
        topic_grades[t] = set()
    topic_grades[t].add(g)

# Build result structure
result = {"by_grade": {}, "by_topic": {}}
for g in sorted(grade_topics.keys(), key=lambda x: int(x) if x.isdigit() else 999):
    result["by_grade"][g] = sorted(grade_topics[g])

for t in sorted(topic_grades.keys()):
    result["by_topic"][t] = sorted(topic_grades[t], key=lambda x: int(x) if x.isdigit() else 999)

with open('_grade_map_result.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("Done - written to _grade_map_result.json")
