# -*- coding: utf-8 -*-
"""
Быстрое переназначение уровней в problems.py через замену текста
"""
import sys
import codecs
import re

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

print("="*70)
print("Быстрое переназначение уровней 6-10 на 1-5")
print("="*70)

# Читаем файл
print("\nЧитаем problems.py...")
with open('problems.py', 'r', encoding='utf-8') as f:
    content = f.read()

print(f"Размер файла: {len(content)} символов")

# Подсчитываем замены
replacements = {
    '"difficulty": 10': '"difficulty": 5',
    '"difficulty": 9': '"difficulty": 5',
    '"difficulty": 8': '"difficulty": 4',
    '"difficulty": 7': '"difficulty": 4',
    '"difficulty": 6': '"difficulty": 3',
}

print("\nВыполняем замены...")
total_replaced = 0
for old, new in replacements.items():
    count = content.count(old)
    if count > 0:
        content = content.replace(old, new)
        print(f"  {old} -> {new}: {count} замен")
        total_replaced += count

print(f"\nВсего замен: {total_replaced}")

# Сохраняем
print("\nСохраняем...")
with open('problems.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Готово!")

# Проверка
print("\nПроверка...")
import importlib
import problems
importlib.reload(problems)
from problems import PROBLEMS_DB
from collections import Counter

levels = Counter(p.get('difficulty') for p in PROBLEMS_DB)
print(f"\nВсего задач: {len(PROBLEMS_DB)}")
print("Уровни после конвертации:")
for level in sorted(levels.keys()):
    print(f"  Уровень {level}: {levels[level]} задач")

print("\n" + "="*70)
print("✅ ЗАВЕРШЕНО!")
print("="*70)
