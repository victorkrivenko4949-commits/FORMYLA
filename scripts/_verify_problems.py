#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from problems import PROBLEMS_DB

print(f"Total tasks: {len(PROBLEMS_DB)}")

# Grade distribution
grades = {}
for p in PROBLEMS_DB:
    g = p.get('grade', '?')
    grades[g] = grades.get(g, 0) + 1
print('\n=== BY GRADE ===')
for g in sorted(grades.keys()):
    print(f'  Grade {g}: {grades[g]}')

# Subject distribution
subjects = {}
for p in PROBLEMS_DB:
    s = p.get('subject', '?')
    subjects[s] = subjects.get(s, 0) + 1
print(f'\n=== BY SUBJECT ({len(subjects)}) ===')
for s, c in sorted(subjects.items(), key=lambda x: -x[1]):
    print(f'  {s}: {c}')

# Subtopic count
subtopics = set(p.get('subtopic', '') for p in PROBLEMS_DB)
print(f'\nUnique subtopics: {len(subtopics)}')

# New tasks
new_tasks = [p for p in PROBLEMS_DB if p['id'] >= 11316]
print(f'\nNew tasks (id >= 11316): {len(new_tasks)}')
if new_tasks:
    s = new_tasks[0]
    print(f'Sample: id={s["id"]}, grade={s["grade"]}, subject={s["subject"]}, subtopic={s["subtopic"]}')
    print(f'  text: {s["text"][:120]}')
    print(f'  answer: {s["answer"][:60]}')
