# -*- coding: utf-8 -*-
"""
Равномерное перераспределение задач по уровням 1-10
Берет задачи из переполненных уровней и распределяет по пустым
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
from collections import Counter

print("="*70)
print("Равномерное перераспределение задач по уровням 1-10")
print("="*70)

# Текущее распределение
current_dist = Counter(p['difficulty'] for p in PROBLEMS_DB)
print("\nТекущее распределение:")
for level in range(1, 11):
    count = current_dist.get(level, 0)
    print(f"  Уровень {level}: {count} задач")

total = len(PROBLEMS_DB)
target_per_level = total // 10  # ~750 задач на уровень

print(f"\nЦель: ~{target_per_level} задач на каждый уровень")

# Создаем бэкап
print("\n💾 Создание бэкапа...")
shutil.copy2("problems.py", "problems.py.before_redistribute.bak")
print("✓ Бэкап: problems.py.before_redistribute.bak")

# Группируем задачи по текущим уровням
problems_by_level = {}
for level in range(1, 11):
    problems_by_level[level] = [p for p in PROBLEMS_DB if p.get('difficulty') == level]

# Перераспределяем
print("\n🔄 Перераспределение...")

# Собираем все задачи в один список
all_problems = []
for level in range(1, 11):
    all_problems.extend(problems_by_level[level])

# Перемешиваем для случайного распределения
random.shuffle(all_problems)

# Распределяем равномерно по уровням
redistributed = []
for i, problem in enumerate(all_problems):
    new_level = (i % 10) + 1  # Уровни 1-10
    problem['difficulty'] = new_level
    redistributed.append(problem)

# Статистика после перераспределения
new_dist = Counter(p['difficulty'] for p in redistributed)

print("\nНовое распределение:")
for level in range(1, 11):
    count = new_dist.get(level, 0)
    print(f"  Уровень {level}: {count} задач")

# Сохраняем
print("\n💾 Сохранение...")
with open("problems.py", 'w', encoding='utf-8') as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write(f"# База задач — {len(redistributed)} задач\n")
    f.write("# Равномерно распределено по уровням 1-10\n\n")
    f.write("PROBLEMS_DB = ")
    json.dump(redistributed, f, ensure_ascii=False, indent=0)
    f.write("\n")

print("✓ Сохранено")

print("\n" + "="*70)
print("✅ ГОТОВО!")
print("="*70)
print(f"\nВсе {len(redistributed)} задач равномерно распределены по 10 уровням")
print(f"Каждый уровень: ~{target_per_level} задач")
print("\nПерезапустите Flask приложение:")
print("  python app.py")
