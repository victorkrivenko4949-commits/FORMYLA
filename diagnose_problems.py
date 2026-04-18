#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Диагностика раздела "Задачи по темам"
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from problems import PROBLEMS_DB

print("=" * 80)
print("ДИАГНОСТИКА РАЗДЕЛА 'ЗАДАЧИ ПО ТЕМАМ'")
print("=" * 80)

# 1. Общая статистика
print(f"\n📊 Всего задач в PROBLEMS_DB: {len(PROBLEMS_DB)}")

# 2. Проверка структуры первой задачи
if PROBLEMS_DB:
    print(f"\n🔍 Структура первой задачи:")
    first = PROBLEMS_DB[0]
    for key, value in first.items():
        if isinstance(value, str) and len(value) > 100:
            print(f"  {key}: {value[:100]}...")
        else:
            print(f"  {key}: {value}")

# 3. Статистика по предметам (subjects)
subjects_count = {}
for p in PROBLEMS_DB:
    subj = p.get('subject', 'unknown')
    subjects_count[subj] = subjects_count.get(subj, 0) + 1

print(f"\n📚 Распределение по предметам:")
for subj, count in sorted(subjects_count.items(), key=lambda x: -x[1]):
    print(f"  {subj}: {count} задач")

# 4. Статистика по подтемам (subtopics)
subtopics_count = {}
for p in PROBLEMS_DB:
    subtopic = p.get('subtopic', 'unknown')
    subtopics_count[subtopic] = subtopics_count.get(subtopic, 0) + 1

print(f"\n🎯 Распределение по подтемам (топ-10):")
for subtopic, count in sorted(subtopics_count.items(), key=lambda x: -x[1])[:10]:
    print(f"  {subtopic}: {count} задач")

# 5. Статистика по классам
grades_count = {}
for p in PROBLEMS_DB:
    grade = p.get('grade', 'unknown')
    grades_count[grade] = grades_count.get(grade, 0) + 1

print(f"\n🎓 Распределение по классам:")
for grade in sorted(grades_count.keys()):
    print(f"  {grade} класс: {grades_count[grade]} задач")

# 6. Статистика по уровням сложности
difficulty_count = {}
for p in PROBLEMS_DB:
    diff = p.get('difficulty', 'unknown')
    difficulty_count[diff] = difficulty_count.get(diff, 0) + 1

print(f"\n⭐ Распределение по уровням сложности:")
for diff in sorted(difficulty_count.keys()):
    print(f"  Уровень {diff}: {difficulty_count[diff]} задач")

# 7. Проверка поля is_active
active_count = sum(1 for p in PROBLEMS_DB if p.get('is_active', True))
inactive_count = len(PROBLEMS_DB) - active_count

print(f"\n✅ Активные задачи: {active_count}")
print(f"❌ Неактивные задачи: {inactive_count}")

# 8. Пример задач для каждого предмета
print(f"\n📝 Примеры задач по предметам:")
shown_subjects = set()
for p in PROBLEMS_DB:
    subj = p.get('subject', 'unknown')
    if subj not in shown_subjects:
        shown_subjects.add(subj)
        print(f"\n  [{subj}] Класс {p.get('grade')}, Уровень {p.get('difficulty')}:")
        print(f"    {p.get('text', '')[:150]}...")
        if len(shown_subjects) >= 5:
            break

# 9. Проверка конкретного примера для отладки маршрута
print(f"\n🔧 Проверка фильтрации (algebra, класс 8, уровень 3):")
filtered = [p for p in PROBLEMS_DB 
            if p.get('subject') == 'algebra' 
            and p.get('grade') == 8 
            and p.get('difficulty') == 3
            and p.get('is_active', True)]
print(f"  Найдено задач: {len(filtered)}")
if filtered:
    print(f"  Пример: {filtered[0].get('text', '')[:100]}...")

print("\n" + "=" * 80)
