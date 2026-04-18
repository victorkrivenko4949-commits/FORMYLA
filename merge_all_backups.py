#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Объединение всех бэкапов задач в один файл problems.py
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import json
from collections import defaultdict

print("=" * 80)
print("ОБЪЕДИНЕНИЕ ВСЕХ БЭКАПОВ ЗАДАЧ")
print("=" * 80)

all_tasks = []
sources = {}

# 1. Текущий problems.py
print("\n📂 Читаем текущий problems.py...")
try:
    from problems import PROBLEMS_DB
    all_tasks.extend(PROBLEMS_DB)
    sources['problems.py'] = len(PROBLEMS_DB)
    print(f"  ✅ Загружено: {len(PROBLEMS_DB)} задач")
except Exception as e:
    print(f"  ❌ Ошибка: {e}")

# 2. problems_ORIGINAL.py
print("\n📂 Читаем problems_ORIGINAL.py...")
try:
    with open('problems_ORIGINAL.py', 'r', encoding='utf-8') as f:
        content = f.read()
    exec_globals = {}
    exec(content, exec_globals)
    if 'PROBLEMS_DB' in exec_globals:
        original_tasks = exec_globals['PROBLEMS_DB']
        all_tasks.extend(original_tasks)
        sources['problems_ORIGINAL.py'] = len(original_tasks)
        print(f"  ✅ Загружено: {len(original_tasks)} задач")
except Exception as e:
    print(f"  ❌ Ошибка: {e}")

# 3. problems_backup_BROKEN.py
print("\n📂 Читаем problems_backup_BROKEN.py...")
try:
    with open('problems_backup_BROKEN.py', 'r', encoding='utf-8') as f:
        content = f.read()
    exec_globals = {}
    exec(content, exec_globals)
    if 'PROBLEMS_DB' in exec_globals:
        broken_tasks = exec_globals['PROBLEMS_DB']
        all_tasks.extend(broken_tasks)
        sources['problems_backup_BROKEN.py'] = len(broken_tasks)
        print(f"  ✅ Загружено: {len(broken_tasks)} задач")
except Exception as e:
    print(f"  ❌ Ошибка: {e}")

# 4. problems_normalized.py
print("\n📂 Читаем problems_normalized.py...")
try:
    with open('problems_normalized.py', 'r', encoding='utf-8') as f:
        content = f.read()
    exec_globals = {}
    exec(content, exec_globals)
    if 'PROBLEMS_DB' in exec_globals:
        norm_tasks = exec_globals['PROBLEMS_DB']
        all_tasks.extend(norm_tasks)
        sources['problems_normalized.py'] = len(norm_tasks)
        print(f"  ✅ Загружено: {len(norm_tasks)} задач")
except Exception as e:
    print(f"  ❌ Ошибка: {e}")

print(f"\n📊 Всего задач до дедупликации: {len(all_tasks)}")
print(f"📊 Источников: {len(sources)}")
for source, count in sources.items():
    print(f"  - {source}: {count} задач")

# Дедупликация по тексту задачи
print("\n🔄 Дедупликация...")
unique_tasks = {}
for task in all_tasks:
    # Используем текст задачи как ключ для дедупликации
    text = task.get('text', '')
    if text and text not in unique_tasks:
        unique_tasks[text] = task

deduplicated = list(unique_tasks.values())
print(f"  ✅ После дедупликации: {len(deduplicated)} уникальных задач")
print(f"  🗑️  Удалено дубликатов: {len(all_tasks) - len(deduplicated)}")

# Статистика по классам
print("\n📚 Распределение по классам:")
by_grade = defaultdict(int)
for task in deduplicated:
    grade = task.get('grade', 'unknown')
    by_grade[grade] += 1

for grade in sorted(by_grade.keys()):
    print(f"  Класс {grade}: {by_grade[grade]} задач")

# Сохраняем в problems.py
print("\n💾 Сохранение в problems.py...")
with open('problems.py', 'w', encoding='utf-8') as f:
    f.write('# -*- coding: utf-8 -*-\n')
    f.write('"""\n')
    f.write('База задач по темам (объединенная из всех бэкапов)\n')
    f.write(f'Всего задач: {len(deduplicated)}\n')
    f.write('"""\n\n')
    f.write('PROBLEMS_DB = ')
    f.write(json.dumps(deduplicated, ensure_ascii=False, indent=2))
    f.write('\n')

print(f"✅ Файл problems.py обновлен! Всего задач: {len(deduplicated)}")

print("\n" + "=" * 80)
print("✅ ОБЪЕДИНЕНИЕ ЗАВЕРШЕНО")
print("=" * 80)
print("\nТеперь запустите analyze_gaps.py чтобы проверить, сколько дырок осталось!")
print("=" * 80)
