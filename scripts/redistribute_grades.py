# -*- coding: utf-8 -*-
"""
Равномерное перераспределение задач по классам 5-11 и уровням 1-10
"""
import sys
import os
import codecs
import json
import shutil
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from problems import PROBLEMS_DB

print("="*70)
print("Равномерное перераспределение по классам 5-11 и уровням 1-10")
print("="*70)

# Создаем бэкап
print("\n💾 Создание бэкапа...")
shutil.copy2("problems.py", "problems.py.before_grade_redistribute.bak")
print("✓ Бэкап: problems.py.before_grade_redistribute.bak")

# Перемешиваем задачи
print("\n🔄 Перемешивание и перераспределение...")
random.shuffle(PROBLEMS_DB)

# Распределяем по классам и уровням
grades = [5, 6, 7, 8, 9, 10, 11]
levels = list(range(1, 11))

for i, problem in enumerate(PROBLEMS_DB):
    # Равномерно по классам
    grade_index = i % len(grades)
    problem['grade'] = grades[grade_index]
    
    # Равномерно по уровням
    level_index = i % len(levels)
    problem['difficulty'] = levels[level_index]
    
    # Переназначаем ID
    problem['id'] = i + 1

# Статистика
from collections import Counter

grade_dist = Counter(p['grade'] for p in PROBLEMS_DB)
level_dist = Counter(p['difficulty'] for p in PROBLEMS_DB)

print("\nРаспределение по классам:")
for grade in grades:
    count = grade_dist.get(grade, 0)
    print(f"  {grade} класс: {count} задач")

print("\nРаспределение по уровням:")
for level in levels:
    count = level_dist.get(level, 0)
    print(f"  Уровень {level}: {count} задач")

# Сохраняем
print("\n💾 Сохранение...")
with open("problems.py", 'w', encoding='utf-8') as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write(f"# База задач — {len(PROBLEMS_DB)} задач\n")
    f.write("# Равномерно распределено по классам 5-11 и уровням 1-10\n\n")
    f.write("PROBLEMS_DB = ")
    json.dump(PROBLEMS_DB, f, ensure_ascii=False, indent=0)
    f.write("\n")

print("✓ Сохранено")

print("\n" + "="*70)
print("✅ ГОТОВО!")
print("="*70)
print(f"\nВсе {len(PROBLEMS_DB)} задач равномерно распределены:")
print(f"  По 7 классам (5-11): ~{len(PROBLEMS_DB)//7} задач на класс")
print(f"  По 10 уровням (1-10): ~{len(PROBLEMS_DB)//10} задач на уровень")
print("\nПерезапустите Flask приложение!")
