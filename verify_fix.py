#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Проверка исправления раздела "Задачи по темам"
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from problems import PROBLEMS_DB

print("=" * 80)
print("ПРОВЕРКА ИСПРАВЛЕНИЯ")
print("=" * 80)

# 1. Общая статистика
print(f"\n📊 Всего задач: {len(PROBLEMS_DB)}")

# 2. Распределение по уровням
difficulty_count = {}
for p in PROBLEMS_DB:
    diff = p.get('difficulty', 'unknown')
    difficulty_count[diff] = difficulty_count.get(diff, 0) + 1

print(f"\n⭐ Распределение по уровням сложности:")
for diff in sorted(difficulty_count.keys()):
    print(f"  Уровень {diff}: {difficulty_count[diff]} задач")

# 3. Проверка доступности задач для разных комбинаций
test_cases = [
    ('algebra', 'Уравнения', 8, 3),
    ('geometry', 'Треугольники', 7, 2),
    ('number_theory', 'Делимость', 6, 4),
    ('combinatorics', 'Подсчёт и перебор', 5, 1),
]

print(f"\n🔧 Проверка доступности задач:")
for subject, subtopic, grade, level in test_cases:
    filtered = [p for p in PROBLEMS_DB 
                if p.get('subject') == subject 
                and p.get('subtopic') == subtopic
                and p.get('grade') == grade 
                and p.get('difficulty') == level]
    print(f"  [{subject}] {subtopic}, класс {grade}, уровень {level}: {len(filtered)} задач")
    if filtered:
        print(f"    Пример: {filtered[0].get('text', '')[:80]}...")

# 4. Статистика по предметам и классам
print(f"\n📚 Задачи по предметам и классам:")
subjects = ['algebra', 'geometry', 'number_theory', 'combinatorics', 'movement', 'knights_liars']
grades = [5, 6, 7, 8, 9]

for subject in subjects:
    subject_tasks = [p for p in PROBLEMS_DB if p.get('subject') == subject]
    if subject_tasks:
        print(f"\n  {subject.upper()}: {len(subject_tasks)} задач")
        for grade in grades:
            grade_tasks = [p for p in subject_tasks if p.get('grade') == grade]
            if grade_tasks:
                levels_dist = {}
                for p in grade_tasks:
                    lev = p.get('difficulty', 0)
                    levels_dist[lev] = levels_dist.get(lev, 0) + 1
                levels_str = ', '.join([f"L{k}:{v}" for k, v in sorted(levels_dist.items())])
                print(f"    Класс {grade}: {len(grade_tasks)} задач ({levels_str})")

print("\n" + "=" * 80)
print("✅ ПРОВЕРКА ЗАВЕРШЕНА")
print("=" * 80)
print("\n💡 Теперь перезапустите Flask-приложение:")
print("   python app.py")
print("\nИ проверьте раздел 'Задачи по темам' на сайте!")
print("=" * 80)
