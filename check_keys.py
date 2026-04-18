#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Проверка реальных ключей в problems.py"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from problems import PROBLEMS_DB
from pprint import pprint
from collections import Counter

print("=" * 80)
print("ПРОВЕРКА РЕАЛЬНЫХ КЛЮЧЕЙ В PROBLEMS.PY")
print("=" * 80)

# Примеры задач
print("\n📝 Примеры задач из базы (первые 10):")
for i, p in enumerate(PROBLEMS_DB[:10]):
    print(f"  {i}: subject='{p.get('subject')}', subtopic='{p.get('subtopic')}', grade={p.get('grade')}, difficulty={p.get('difficulty')}")

# Все уникальные subtopic
unique_subtopics = set(p.get("subtopic") for p in PROBLEMS_DB)
print(f"\n🔑 Все уникальные subtopic ({len(unique_subtopics)} шт):")
for st in sorted(unique_subtopics):
    print(f"  - '{st}'")

# Подсчет задач по subtopic
subtopic_counts = Counter(p.get("subtopic") for p in PROBLEMS_DB)
print(f"\n📊 Количество задач по subtopic:")
for st, count in sorted(subtopic_counts.items(), key=lambda x: -x[1]):
    print(f"  '{st}': {count} задач")

# Группировка по subject
print(f"\n📚 Subtopic по предметам:")
by_subject = {}
for p in PROBLEMS_DB:
    subj = p.get('subject')
    st = p.get('subtopic')
    if subj not in by_subject:
        by_subject[subj] = set()
    by_subject[subj].add(st)

for subj in sorted(by_subject.keys()):
    print(f"\n{subj}:")
    for st in sorted(by_subject[subj]):
        count = subtopic_counts[st]
        print(f"  - '{st}': {count} задач")

print("\n" + "=" * 80)
