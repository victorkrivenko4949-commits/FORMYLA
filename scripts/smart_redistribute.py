# -*- coding: utf-8 -*-
"""
Умное перераспределение задач:
- Младшие классы (5-7) → Уровни 1-5
- Средние классы (8-9) → Уровни 3-8
- Старшие классы (10-11) → Уровни 6-10
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

# Маппинг классов на допустимые уровни
GRADE_TO_LEVELS = {
    5: [1, 2, 3, 4, 5],      # Младшие: простые уровни
    6: [1, 2, 3, 4, 5, 6],   # Младшие: простые + средние
    7: [2, 3, 4, 5, 6, 7],   # Средние
    8: [3, 4, 5, 6, 7, 8],   # Средние
    9: [4, 5, 6, 7, 8, 9],   # Средние + сложные
    10: [6, 7, 8, 9, 10],    # Старшие: сложные уровни
    11: [7, 8, 9, 10],       # Старшие: только сложные
}

print("="*70)
print("Умное перераспределение задач")
print("="*70)
print("\nЛогика:")
print("  5-6 классы → Уровни 1-6 (простые)")
print("  7-9 классы → Уровни 2-9 (средние)")
print("  10-11 классы → Уровни 6-10 (сложные)")

# Создаем бэкап
print("\n💾 Создание бэкапа...")
shutil.copy2("problems.py", "problems.py.before_smart.bak")
print("✓ Бэкап: problems.py.before_smart.bak")

# Группируем задачи по классам
print("\n🔄 Перераспределение...")

problems_by_grade = {}
for grade in GRADE_TO_LEVELS.keys():
    problems_by_grade[grade] = [p for p in PROBLEMS_DB if p.get('grade') == grade]

# Перераспределяем уровни внутри каждого класса
redistributed = []

for grade, problems in problems_by_grade.items():
    allowed_levels = GRADE_TO_LEVELS[grade]
    
    # Перемешиваем задачи
    random.shuffle(problems)
    
    # Распределяем по допустимым уровням
    for i, problem in enumerate(problems):
        level_index = i % len(allowed_levels)
        problem['difficulty'] = allowed_levels[level_index]
        redistributed.append(problem)

# Переназначаем ID
for i, problem in enumerate(redistributed, 1):
    problem['id'] = i

print(f"✓ Перераспределено {len(redistributed)} задач")

# Статистика
from collections import Counter

grade_dist = Counter(p['grade'] for p in redistributed)
level_dist = Counter(p['difficulty'] for p in redistributed)

print("\n📊 Распределение по классам:")
for grade in sorted(GRADE_TO_LEVELS.keys()):
    count = grade_dist.get(grade, 0)
    levels = GRADE_TO_LEVELS[grade]
    print(f"  {grade} класс: {count} задач (уровни {min(levels)}-{max(levels)})")

print("\n📊 Распределение по уровням:")
for level in range(1, 11):
    count = level_dist.get(level, 0)
    print(f"  Уровень {level}: {count} задач")

# Сохраняем
print("\n💾 Сохранение...")
with open("problems.py", 'w', encoding='utf-8') as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write(f"# База задач — {len(redistributed)} задач\n")
    f.write("# Умное распределение: младшие классы = простые уровни\n\n")
    f.write("PROBLEMS_DB = ")
    json.dump(redistributed, f, ensure_ascii=False, indent=0)
    f.write("\n")

print("✓ Сохранено")

print("\n" + "="*70)
print("✅ ГОТОВО!")
print("="*70)
print(f"\nВсе {len(redistributed)} задач перераспределены логично:")
print("  5-6 классы: простые уровни")
print("  7-9 классы: средние уровни")
print("  10-11 классы: сложные уровни")
print("\nПерезапустите Flask!")
