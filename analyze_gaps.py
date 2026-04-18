#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Анализ пробелов в базе задач
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
print("АНАЛИЗ ПРОБЕЛОВ В БАЗЕ ЗАДАЧ")
print("=" * 80)

# Считаем задачи в каждой ячейке
cells = Counter()
for p in PROBLEMS_DB:
    key = (p.get("subject"), p.get("subtopic"), p.get("grade"), p.get("difficulty"))
    cells[key] += 1

print(f"\n📊 Всего уникальных ячеек с задачами: {len(cells)}")
print(f"📊 Всего задач: {len(PROBLEMS_DB)}")

# Находим дырки
gaps = []
for subject_key, subtopics_dict in SUBTOPICS.items():
    for subtopic_key, subtopic_title in subtopics_dict.items():
        for grade in range(5, 12):  # 5-11 классы
            for level in range(1, 8):  # 1-7 уровни
                count = cells.get((subject_key, subtopic_title, grade, level), 0)
                if count < 3:
                    need = 3 - count
                    gaps.append({
                        "subject": subject_key,
                        "subtopic": subtopic_title,
                        "grade": grade,
                        "level": level,
                        "have": count,
                        "need": need
                    })

print(f"\n❌ Всего дырок (ячеек с < 3 задачами): {len(gaps)}")
print(f"📝 Нужно догенерировать задач: {sum(g['need'] for g in gaps)}")

# Статистика по классам
print(f"\n📚 Статистика по классам:")
for grade in range(5, 12):
    grade_gaps = [g for g in gaps if g['grade'] == grade]
    grade_tasks = [p for p in PROBLEMS_DB if p.get('grade') == grade]
    print(f"  Класс {grade}: {len(grade_tasks)} задач, {len(grade_gaps)} дырок, нужно +{sum(g['need'] for g in grade_gaps)} задач")

# Топ-10 самых пустых предметов/подтем
print(f"\n🔝 Топ-10 самых пустых комбинаций (subject + subtopic):")
subject_subtopic_gaps = Counter()
for g in gaps:
    key = (g['subject'], g['subtopic'])
    subject_subtopic_gaps[key] += g['need']

for (subj, subtopic), need in subject_subtopic_gaps.most_common(10):
    print(f"  [{subj}] {subtopic}: нужно +{need} задач")

# Сохраняем список дырок для fill_gaps.py
import json
with open('gaps_list.json', 'w', encoding='utf-8') as f:
    json.dump(gaps, f, ensure_ascii=False, indent=2)

print(f"\n💾 Список дырок сохранен в gaps_list.json")
print("=" * 80)
