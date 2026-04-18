#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Исправление уровней сложности в PROBLEMS_DB
Все задачи имеют difficulty=10, нужно распределить их на уровни 1-7
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import json
import random

# Читаем problems.py
with open('problems.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Извлекаем PROBLEMS_DB
exec(content)

print("=" * 80)
print("ИСПРАВЛЕНИЕ УРОВНЕЙ СЛОЖНОСТИ")
print("=" * 80)

print(f"\n📊 Всего задач: {len(PROBLEMS_DB)}")
print(f"❌ Задач с difficulty=10: {sum(1 for p in PROBLEMS_DB if p.get('difficulty') == 10)}")

# Стратегия распределения:
# Для каждой комбинации (subject, subtopic, grade) распределяем задачи равномерно по уровням 1-7

from collections import defaultdict

# Группируем задачи
groups = defaultdict(list)
for p in PROBLEMS_DB:
    key = (p.get('subject'), p.get('subtopic'), p.get('grade'))
    groups[key].append(p)

print(f"\n🔧 Найдено уникальных групп (subject, subtopic, grade): {len(groups)}")

# Распределяем задачи в каждой группе по уровням 1-7
fixed_count = 0
for key, tasks in groups.items():
    # Перемешиваем для случайности
    random.shuffle(tasks)
    
    # Распределяем равномерно по 7 уровням
    tasks_per_level = len(tasks) // 7
    remainder = len(tasks) % 7
    
    idx = 0
    for level in range(1, 8):
        # Количество задач для этого уровня
        count = tasks_per_level + (1 if level <= remainder else 0)
        
        # Назначаем уровень
        for i in range(count):
            if idx < len(tasks):
                tasks[idx]['difficulty'] = level
                fixed_count += 1
                idx += 1

print(f"✅ Исправлено задач: {fixed_count}")

# Проверяем распределение
difficulty_count = {}
for p in PROBLEMS_DB:
    diff = p.get('difficulty', 'unknown')
    difficulty_count[diff] = difficulty_count.get(diff, 0) + 1

print(f"\n⭐ Новое распределение по уровням:")
for diff in sorted(difficulty_count.keys()):
    print(f"  Уровень {diff}: {difficulty_count[diff]} задач")

# Сохраняем обновленный problems.py
print(f"\n💾 Сохранение в problems.py...")

with open('problems.py', 'w', encoding='utf-8') as f:
    f.write('# -*- coding: utf-8 -*-\n')
    f.write('"""\n')
    f.write('База задач по темам (2500 задач с HuggingFace)\n')
    f.write('Уровни сложности исправлены: 1-7 вместо 10\n')
    f.write('"""\n\n')
    f.write('PROBLEMS_DB = ')
    f.write(json.dumps(PROBLEMS_DB, ensure_ascii=False, indent=2))
    f.write('\n')

print(f"✅ Файл problems.py обновлен!")

# Проверка: сколько задач теперь доступно для algebra, класс 8, уровень 3
test_filtered = [p for p in PROBLEMS_DB 
                 if p.get('subject') == 'algebra' 
                 and p.get('grade') == 8 
                 and p.get('difficulty') == 3]
print(f"\n🔧 Проверка: algebra, класс 8, уровень 3 → {len(test_filtered)} задач")

print("\n" + "=" * 80)
print("✅ ГОТОВО! Перезапустите Flask-приложение для применения изменений.")
print("=" * 80)
