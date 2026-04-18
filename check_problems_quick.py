#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Быстрая проверка problems.py
"""
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from problems import PROBLEMS_DB

print("=" * 80)
print("ПРОВЕРКА PROBLEMS.PY")
print("=" * 80)

print(f"\n📊 Всего задач: {len(PROBLEMS_DB)}")

# Проверка уровней
levels = {}
for task in PROBLEMS_DB:
    level = task.get('level', 'unknown')
    levels[level] = levels.get(level, 0) + 1

print(f"\n📈 Распределение по уровням:")
for level in sorted(levels.keys()):
    print(f"   Уровень {level}: {levels[level]} задач")

# Проверка первой задачи
print(f"\n📝 Пример первой задачи:")
first = PROBLEMS_DB[0]
print(f"   ID: {first.get('id')}")
print(f"   Уровень: {first.get('level')}")
print(f"   Тема: {first.get('topic', 'N/A')[:50]}")
print(f"   Текст: {first.get('text', 'N/A')[:100]}...")

# Проверка на уровень 10
level_10_count = sum(1 for task in PROBLEMS_DB if task.get('level') == 10)
if level_10_count > 0:
    print(f"\n⚠️  ВНИМАНИЕ: Найдено {level_10_count} задач с уровнем 10!")
else:
    print(f"\n✅ Отлично! Нет задач с уровнем 10")

print("\n" + "=" * 80)
if len(PROBLEMS_DB) == 2305 and level_10_count == 0:
    print("✅ ВСЁ ИДЕАЛЬНО! Можно запускать safe_wrap_latex.py")
else:
    print(f"⚠️  Проверьте: ожидалось 2305 задач, найдено {len(PROBLEMS_DB)}")
print("=" * 80)
