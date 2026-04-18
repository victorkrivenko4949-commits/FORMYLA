#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Отладка: почему задачи не находятся
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from problems import PROBLEMS_DB

# Структура из app.py
SUBJECTS = {
    "algebra": "Алгебра",
    "geometry": "Геометрия",
    "number_theory": "Теория чисел",
    "combinatorics": "Комбинаторика",
    "knights_liars": "Рыцари и лжецы",
    "movement": "Задачи на движение"
}

SUBTOPICS = {
    "algebra": {
        "equations": "Уравнения",
        "inequalities": "Неравенства",
        "other_algebra": "Другие задачи",
        "text_problems": "Текстовые задачи"
    }
}

GRADES = [5, 6, 7, 8, 9, 10, 11]

print("=" * 80)
print("ОТЛАДКА СООТВЕТСТВИЯ ЗАДАЧ")
print("=" * 80)

# Проверяем первые 5 задач
print("\n🔍 Первые 5 задач из PROBLEMS_DB:")
for i, p in enumerate(PROBLEMS_DB[:5]):
    print(f"\nЗадача {i+1}:")
    print(f"  subject: '{p.get('subject')}'")
    print(f"  subtopic: '{p.get('subtopic')}'")
    print(f"  grade: {p.get('grade')} (тип: {type(p.get('grade')).__name__})")
    print(f"  difficulty: {p.get('difficulty')} (тип: {type(p.get('difficulty')).__name__})")

# Проверяем уникальные значения subtopic
unique_subtopics = set()
for p in PROBLEMS_DB:
    unique_subtopics.add(p.get('subtopic'))

print(f"\n📋 Уникальные subtopic в PROBLEMS_DB ({len(unique_subtopics)}):")
for st in sorted(unique_subtopics)[:20]:  # Первые 20
    print(f"  - '{st}'")

# Тестовый запрос как в app.py (с английским ключом)
print(f"\n🧪 Тест 1: (algebra, equations, класс 8, уровень 3):")
test1 = [p for p in PROBLEMS_DB
         if p.get("subject") == "algebra"
         and p.get("subtopic") == "equations"
         and p.get("grade") == 8
         and p.get("difficulty") == 3]
print(f"  Найдено: {len(test1)} задач")

# Тестовый запрос с русским названием
print(f"\n🧪 Тест 2: (algebra, 'Уравнения', класс 8, уровень 3):")
test2 = [p for p in PROBLEMS_DB
         if p.get("subject") == "algebra"
         and p.get("subtopic") == "Уравнения"
         and p.get("grade") == 8
         and p.get("difficulty") == 3]
print(f"  Найдено: {len(test2)} задач")

# Проверка: есть ли вообще задачи по алгебре 8 класса уровня 3
print(f"\n🧪 Тест 3: (algebra, любая subtopic, класс 8, уровень 3):")
test3 = [p for p in PROBLEMS_DB
         if p.get("subject") == "algebra"
         and p.get("grade") == 8
         and p.get("difficulty") == 3]
print(f"  Найдено: {len(test3)} задач")
if test3:
    print(f"  Примеры subtopic: {set(p.get('subtopic') for p in test3[:5])}")

print("\n" + "=" * 80)
print("❌ ПРОБЛЕМА: subtopic в PROBLEMS_DB использует РУССКИЕ названия,")
print("   а app.py ищет по АНГЛИЙСКИМ ключам (equations, inequalities)!")
print("=" * 80)
