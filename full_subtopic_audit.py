#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Полный аудит маппинга подтем между БД и app.py
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from problems import PROBLEMS_DB
from collections import Counter

# Структура из app.py
SUBTOPICS = {
    "algebra": {
        "equations": "Уравнения",
        "inequalities": "Неравенства",
        "other_algebra": "Другие задачи",
        "text_problems": "Текстовые задачи"
    },
    "geometry": {
        "basics": "Основы геометрии",
        "circles": "Окружности",
        "triangles": "Треугольники",
        "other_geometry": "Другие задачи"
    },
    "number_theory": {
        "divisibility": "Делимость",
        "primes_and_equations": "Простые числа и уравнения",
        "other_number_theory": "Другие задачи"
    },
    "combinatorics": {
        "dirichlet_and_graphs": "Принцип Дирихле и графы",
        "games": "Игры и инварианты",
        "other_combinatorics": "Другие задачи"
    },
    "movement": {
        "movement_all": "Задачи на движение"
    },
    "knights_liars": {
        "logic_all": "Логические задачи"
    }
}

print("=" * 80)
print("ПОЛНЫЙ АУДИТ МАППИНГА ПОДТЕМ")
print("=" * 80)

# 1. Подтемы в БД
subtopics_in_db = {}
for p in PROBLEMS_DB:
    subject = p.get("subject")
    subtopic = p.get("subtopic")
    key = (subject, subtopic)
    if key not in subtopics_in_db:
        subtopics_in_db[key] = 0
    subtopics_in_db[key] += 1

print(f"\n📊 Подтемы в базе данных (всего {len(subtopics_in_db)} уникальных):")
for (subject, subtopic), count in sorted(subtopics_in_db.items()):
    print(f"  [{subject}] '{subtopic}': {count} задач")

# 2. Подтемы в app.py
print(f"\n📋 Подтемы в app.py (русские названия):")
app_subtopics = {}
for subject, subs in SUBTOPICS.items():
    for key, title in subs.items():
        print(f"  [{subject}] key='{key}' → title='{title}'")
        app_subtopics[(subject, title)] = key

# 3. Сравнение
print(f"\n❌ НЕСОВПАДЕНИЯ:")

print(f"\n1️⃣ Подтемы ЕСТЬ в БД, но НЕТ в app.py (задачи не показываются):")
missing_in_app = []
for (subject, subtopic), count in sorted(subtopics_in_db.items()):
    if (subject, subtopic) not in app_subtopics:
        missing_in_app.append((subject, subtopic, count))
        print(f"  ❌ [{subject}] '{subtopic}': {count} задач НЕ ОТОБРАЖАЮТСЯ")

print(f"\n2️⃣ Подтемы ЕСТЬ в app.py, но НЕТ в БД (разделы пустые):")
missing_in_db = []
for (subject, title), key in sorted(app_subtopics.items()):
    if (subject, title) not in subtopics_in_db:
        missing_in_db.append((subject, title, key))
        print(f"  ❌ [{subject}] '{title}' (key='{key}'): 0 задач")

# 4. Предложения по маппингу
print(f"\n💡 ПРЕДЛОЖЕНИЯ ПО ИСПРАВЛЕНИЮ:")

if missing_in_app:
    print(f"\nДобавить в SUBTOPICS в app.py:")
    for subject, subtopic, count in missing_in_app:
        # Генерируем ключ из названия
        key = subtopic.lower().replace(" ", "_").replace("ё", "е")
        print(f'  "{subject}": {{')
        print(f'    "{key}": "{subtopic}",  # {count} задач')
        print(f'  }}')

# 5. Детальная статистика по каждому subject
print(f"\n📚 ДЕТАЛЬНАЯ СТАТИСТИКА ПО ПРЕДМЕТАМ:")
for subject in ["algebra", "geometry", "number_theory", "combinatorics", "movement", "knights_liars"]:
    print(f"\n{subject.upper()}:")
    subject_tasks = [(st, cnt) for (subj, st), cnt in subtopics_in_db.items() if subj == subject]
    if subject_tasks:
        for subtopic, count in sorted(subject_tasks, key=lambda x: -x[1]):
            # Проверяем, есть ли в app.py
            in_app = "✅" if (subject, subtopic) in app_subtopics else "❌"
            print(f"  {in_app} '{subtopic}': {count} задач")
    else:
        print(f"  (нет задач)")

print("\n" + "=" * 80)
