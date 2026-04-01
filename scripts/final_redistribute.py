# -*- coding: utf-8 -*-
"""
Финальное равномерное распределение задач
По всем разделам, подтемам, классам и уровням
"""
import sys
import os
import json
import shutil
import codecs
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from problems import PROBLEMS_DB

# Финальная структура из app.py
FINAL_STRUCTURE = {
    "algebra": ["equations", "inequalities", "text_problems", "other_algebra"],
    "geometry": ["basics", "triangles", "circles", "other_geometry"],
    "combinatorics": ["dirichlet_and_graphs", "games", "other_combinatorics"],
    "number_theory": ["divisibility", "primes_and_equations", "other_number_theory"],
    "movement": ["movement_all"],
    "knights_liars": ["logic_all"]
}

GRADES = [5, 6, 7, 8, 9, 10, 11]
LEVELS = list(range(1, 11))

print("="*70)
print("Финальное равномерное распределение")
print("="*70)

# Создаем бэкап
print("\n💾 Создание бэкапа...")
shutil.copy2("problems.py", "problems.py.final_backup.bak")
print("✓ Бэкап: problems.py.final_backup.bak")

# Перемешиваем все задачи
print("\n🔄 Перемешивание и распределение...")
random.shuffle(PROBLEMS_DB)

# Создаем список всех комбинаций (раздел, подтема)
all_combinations = []
for subject, subtopics in FINAL_STRUCTURE.items():
    for subtopic in subtopics:
        all_combinations.append((subject, subtopic))

# Распределяем задачи
for i, problem in enumerate(PROBLEMS_DB):
    # Раздел и подтема
    combo_index = i % len(all_combinations)
    subject, subtopic = all_combinations[combo_index]
    problem['subject'] = subject
    problem['subtopic'] = subtopic
    
    # Класс
    grade_index = i % len(GRADES)
    problem['grade'] = GRADES[grade_index]
    
    # Уровень
    level_index = i % len(LEVELS)
    problem['difficulty'] = LEVELS[level_index]
    
    # ID
    problem['id'] = i + 1

print(f"✓ Распределено {len(PROBLEMS_DB)} задач")

# Статистика
from collections import Counter

subject_dist = Counter(p['subject'] for p in PROBLEMS_DB)
subtopic_dist = Counter(p['subtopic'] for p in PROBLEMS_DB)
grade_dist = Counter(p['grade'] for p in PROBLEMS_DB)
level_dist = Counter(p['difficulty'] for p in PROBLEMS_DB)

print("\n📊 Распределение по разделам:")
for subj, count in subject_dist.most_common():
    print(f"  {subj}: {count} задач")

print("\n📊 Распределение по подтемам:")
for subtopic, count in subtopic_dist.most_common():
    print(f"  {subtopic}: {count} задач")

print("\n📊 Распределение по классам:")
for grade in GRADES:
    print(f"  {grade} класс: {grade_dist[grade]} задач")

print("\n📊 Распределение по уровням:")
for level in LEVELS:
    print(f"  Уровень {level}: {level_dist[level]} задач")

# Сохраняем
print("\n💾 Сохранение...")
with open("problems.py", 'w', encoding='utf-8') as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write(f"# База задач — {len(PROBLEMS_DB)} задач\n")
    f.write("# Равномерно распределено по всем разделам, подтемам, классам и уровням\n\n")
    f.write("PROBLEMS_DB = ")
    json.dump(PROBLEMS_DB, f, ensure_ascii=False, indent=0)
    f.write("\n")

print("✓ Сохранено")

print("\n" + "="*70)
print("✅ ФИНАЛЬНОЕ РАСПРЕДЕЛЕНИЕ ЗАВЕРШЕНО!")
print("="*70)
print(f"\nВсе {len(PROBLEMS_DB)} задач равномерно распределены")
print("Перезапустите Flask!")
