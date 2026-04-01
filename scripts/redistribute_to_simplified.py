# -*- coding: utf-8 -*-
"""
Перераспределение задач по упрощенной структуре подтем
Теперь в каждом разделе только 2 подтемы: основная + "Разное"
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

# Новая упрощенная структура
SIMPLIFIED_SUBTOPICS = {
    "algebra": ["Уравнения", "Разное"],
    "geometry": ["Треугольники", "Разное"],
    "combinatorics": ["Подсчёт и перебор", "Разное"],
    "number_theory": ["Делимость", "Разное"],
    "knights_liars": ["Задачи с условиями", "Разное"],
    "movement": ["Равномерное движение", "Разное"],
    "other": ["Разное"]
}

print("="*70)
print("Перераспределение задач по упрощенной структуре")
print("="*70)

# Создаем бэкап
print("\n💾 Создание бэкапа...")
shutil.copy2("problems.py", "problems.py.before_simplify.bak")
print("✓ Бэкап: problems.py.before_simplify.bak")

# Группируем задачи по разделам
print("\n🔄 Перераспределение по подтемам...")

problems_by_subject = {}
for subject in SIMPLIFIED_SUBTOPICS.keys():
    problems_by_subject[subject] = [p for p in PROBLEMS_DB if p.get('subject') == subject]

# Перераспределяем задачи внутри каждого раздела
redistributed = []

for subject, subtopics in SIMPLIFIED_SUBTOPICS.items():
    problems = problems_by_subject.get(subject, [])
    
    if not problems:
        continue
    
    # Перемешиваем
    random.shuffle(problems)
    
    # Распределяем по подтемам
    for i, problem in enumerate(problems):
        # Чередуем подтемы
        subtopic_index = i % len(subtopics)
        problem['subtopic'] = subtopics[subtopic_index]
        redistributed.append(problem)

# Переназначаем ID
for i, problem in enumerate(redistributed, 1):
    problem['id'] = i

print(f"✓ Перераспределено {len(redistributed)} задач")

# Статистика
from collections import Counter

subject_dist = Counter(p['subject'] for p in redistributed)
subtopic_dist = Counter(p['subtopic'] for p in redistributed)

print("\n📊 Распределение по разделам:")
for subj, count in subject_dist.most_common():
    print(f"  {subj}: {count} задач")

print("\n📊 Распределение по подтемам:")
for subtopic, count in subtopic_dist.most_common():
    print(f"  {subtopic}: {count} задач")

# Сохраняем
print("\n💾 Сохранение...")
with open("problems.py", 'w', encoding='utf-8') as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write(f"# База задач — {len(redistributed)} задач\n")
    f.write("# Упрощенная структура: 2 подтемы на раздел\n\n")
    f.write("PROBLEMS_DB = ")
    json.dump(redistributed, f, ensure_ascii=False, indent=0)
    f.write("\n")

print("✓ Сохранено")

print("\n" + "="*70)
print("✅ ГОТОВО!")
print("="*70)
print(f"\nВсе {len(redistributed)} задач перераспределены")
print("Теперь в каждом разделе только 2 подтемы")
print("\nПерезапустите Flask и проверьте сайт!")
