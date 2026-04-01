# -*- coding: utf-8 -*-
"""
Умное распределение по подтемам ВНУТРИ каждого раздела
Сохраняет правильную классификацию разделов от DeepSeek
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

# Структура подтем
SUBTOPICS_STRUCTURE = {
    "algebra": ["equations", "inequalities", "text_problems", "other_algebra"],
    "geometry": ["basics", "triangles", "circles", "other_geometry"],
    "combinatorics": ["dirichlet_and_graphs", "games", "other_combinatorics"],
    "number_theory": ["divisibility", "primes_and_equations", "other_number_theory"],
    "movement": ["movement_all"],
    "knights_liars": ["logic_all"],
    "other": ["other_algebra"]
}

print("="*70)
print("Умное распределение по подтемам")
print("="*70)

# Бэкап
print("\n💾 Создание бэкапа...")
shutil.copy2("problems.py", "problems.py.before_smart_subtopics.bak")
print("✓ Бэкап: problems.py.before_smart_subtopics.bak")

# Группируем задачи по разделам
print("\n🔄 Распределение по подтемам внутри каждого раздела...")

problems_by_subject = {}
for subject in SUBTOPICS_STRUCTURE.keys():
    problems_by_subject[subject] = [p for p in PROBLEMS_DB if p.get('subject') == subject]

# Распределяем подтемы внутри каждого раздела
redistributed = []

for subject, subtopics in SUBTOPICS_STRUCTURE.items():
    problems = problems_by_subject.get(subject, [])
    
    if not problems:
        continue
    
    # Перемешиваем задачи этого раздела
    random.shuffle(problems)
    
    # Распределяем по подтемам
    for i, problem in enumerate(problems):
        subtopic_index = i % len(subtopics)
        problem['subtopic'] = subtopics[subtopic_index]
        redistributed.append(problem)

# Конвертируем уровни в 1-5
LEVEL_MAPPING = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4, 9: 5, 10: 5}

for problem in redistributed:
    old_level = problem.get('difficulty', 1)
    new_level = LEVEL_MAPPING.get(old_level, 1)
    problem['difficulty'] = new_level
    
# Переназначаем ID
for i, problem in enumerate(redistributed, 1):
    problem['id'] = i

print(f"✓ Распределено {len(redistributed)} задач")

# Статистика
from collections import Counter

subject_dist = Counter(p['subject'] for p in redistributed)
subtopic_dist = Counter(p['subtopic'] for p in redistributed)
level_dist = Counter(p['difficulty'] for p in redistributed)

print("\n📊 По разделам:")
for subj, count in subject_dist.most_common():
    print(f"  {subj}: {count} задач")

print("\n📊 По подтемам:")
for subtopic, count in subtopic_dist.most_common():
    print(f"  {subtopic}: {count} задач")

print("\n📊 По уровням:")
for level in range(1, 6):
    print(f"  Уровень {level}: {level_dist[level]} задач")

# Сохраняем
print("\n💾 Сохранение...")
with open("problems.py", 'w', encoding='utf-8') as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write(f"# База задач — {len(redistributed)} задач\n")
    f.write("# Разделы от DeepSeek, подтемы распределены равномерно, уровни 1-5\n\n")
    f.write("PROBLEMS_DB = ")
    json.dump(redistributed, f, ensure_ascii=False, indent=0)
    f.write("\n")

print("✓ Сохранено")
print("\n✅ ГОТОВО! Разделы правильные, подтемы равномерные, уровни 1-5")
