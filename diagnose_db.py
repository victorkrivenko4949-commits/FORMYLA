#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Диагностика problems.py (READ ONLY)"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from problems import PROBLEMS_DB
from collections import Counter

print("=" * 80)
print("ДИАГНОСТИКА PROBLEMS.PY (READ ONLY)")
print("=" * 80)

# 1. Сколько задач в базе
print(f"\n📊 Всего задач: {len(PROBLEMS_DB)}")

# 2. Все уникальные значения subject
subjects = Counter(p.get("subject") for p in PROBLEMS_DB)
print(f"\n📚 Subjects:")
for s, c in subjects.most_common():
    print(f"  '{s}': {c} задач")

# 3. Все уникальные значения subtopic
subtopics = Counter(p.get("subtopic") for p in PROBLEMS_DB)
print(f"\n🔑 Subtopics:")
for s, c in subtopics.most_common():
    print(f"  '{s}': {c} задач")

# 4. Все уникальные значения grade
grades = Counter(p.get("grade") for p in PROBLEMS_DB)
print(f"\n🎓 Grades:")
for g, c in sorted(grades.items()):
    print(f"  {g}: {c} задач")

# 5. Все уникальные значения difficulty
diffs = Counter(p.get("difficulty") for p in PROBLEMS_DB)
print(f"\n⭐ Difficulty levels:")
for d, c in sorted(diffs.items()):
    print(f"  {d}: {c} задач")

# 6. Примеры задач
print(f"\n📝 Примеры задач (первые 5):")
for i, p in enumerate(PROBLEMS_DB[:5]):
    print(f"  {i}: subject='{p.get('subject')}', subtopic='{p.get('subtopic')}', grade={p.get('grade')}, difficulty={p.get('difficulty')}")

print("\n" + "=" * 80)
print("ДИАГНОСТИКА ЗАВЕРШЕНА (problems.py НЕ ИЗМЕНЕН)")
print("=" * 80)
