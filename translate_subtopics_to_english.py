#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Перевод subtopic с русского на английские ключи
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import json
from problems import PROBLEMS_DB

# Маппинг русских названий на английские ключи
SUBTOPIC_MAPPING = {
    # Алгебра
    'Уравнения': 'equations',
    'Неравенства': 'inequalities',
    'Системы уравнений': 'systems',
    'Последовательности': 'sequences',
    'Функции': 'functions',
    'Диофантовы уравнения': 'diophantine',
    'Координатная геометрия': 'coordinates',
    'Проценты': 'percents',
    'Разное': 'other',
    
    # Геометрия
    'Треугольники': 'triangles',
    'Окружности': 'circles',
    'Четырёхугольники': 'quadrilaterals',
    'Многоугольники': 'polygons',
    'Площади': 'areas',
    
    # Теория чисел
    'Делимость': 'divisibility',
    'Остатки': 'remainders',
    'Диофантовые уравнения': 'diophantine',
    'Простые числа': 'primes',
    'Классические задачи': 'classic',
    'Сумма цифр': 'digit_sum',
    'Суммы цифр': 'digit_sum',
    'Подсчёт и перебор': 'counting',
    
    # Комбинаторика
    'Графы и раскраски': 'graphs',
    'Принцип Дирихле': 'pigeonhole',
    'Игры и стратегии': 'games',
    'Инварианты': 'invariants',
    'Раскраски': 'colorings',
    'Задачи с условиями': 'conditions',
    
    # Движение
    'Равномерное движение': 'uniform',
    'Движение навстречу и вдогонку': 'meeting',
    'Движение по воде и эскалаторы': 'water',
    
    # Рыцари и лжецы
    'Задачи на острове': 'island',
}

print("=" * 80)
print("ПЕРЕВОД SUBTOPIC НА АНГЛИЙСКИЕ КЛЮЧИ")
print("=" * 80)

print(f"\n📊 Всего задач: {len(PROBLEMS_DB)}")

# Переводим
translated = 0
not_found = set()

for task in PROBLEMS_DB:
    subtopic_ru = task.get('subtopic')
    if subtopic_ru in SUBTOPIC_MAPPING:
        task['subtopic'] = SUBTOPIC_MAPPING[subtopic_ru]
        translated += 1
    else:
        not_found.add(subtopic_ru)

print(f"✅ Переведено: {translated} задач")

if not_found:
    print(f"\n⚠️  Не найдено в маппинге ({len(not_found)} уникальных):")
    for st in sorted(not_found):
        print(f"  - '{st}'")

# Сохраняем
print(f"\n💾 Сохранение в problems.py...")
with open('problems.py', 'w', encoding='utf-8') as f:
    f.write('# -*- coding: utf-8 -*-\n')
    f.write('PROBLEMS_DB = ')
    json.dump(PROBLEMS_DB, f, ensure_ascii=False, indent=2)
    f.write('\n')

print(f"✅ Сохранено!")

# Проверка
from problems import PROBLEMS_DB as NEW_DB
print(f"\n✅ Проверка: {len(NEW_DB)} задач")
print(f"Пример subtopic: '{NEW_DB[0].get('subtopic')}'")

print("\n" + "=" * 80)
