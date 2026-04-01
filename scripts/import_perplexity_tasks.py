# -*- coding: utf-8 -*-
"""
Импорт задач из файла Perplexity с фильтрацией по уровням 1-5
"""
import sys
import os
import json
import codecs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from problems import PROBLEMS_DB

print("="*70)
print("Импорт задач из Perplexity")
print("="*70)

# Читаем файл от Perplexity
input_file = "../../Downloads/all_2285_tasks (1).json"
print(f"\n📄 Читаем файл: {input_file}")

with open(input_file, 'r', encoding='utf-8') as f:
    perplexity_tasks = json.load(f)

print(f"✅ Загружено задач: {len(perplexity_tasks)}")

# Фильтруем только задачи с уровнями 1-5
filtered_tasks = [t for t in perplexity_tasks if t.get('difficulty', 0) <= 5]
print(f"✅ Задач с уровнями 1-5: {len(filtered_tasks)}")

# Проверяем, какие уровни есть
levels = set(t['difficulty'] for t in filtered_tasks)
print(f"📊 Уровни в отфильтрованных задачах: {sorted(levels)}")

# Получаем максимальный ID из текущей базы
max_id = max(p.get('id', 0) for p in PROBLEMS_DB) if PROBLEMS_DB else 0
print(f"\n🆔 Максимальный ID в базе: {max_id}")

# Обновляем ID для новых задач
next_id = max_id + 1
for i, task in enumerate(filtered_tasks):
    task['id'] = next_id + i

print(f"🆔 Новые ID: {next_id} - {next_id + len(filtered_tasks) - 1}")

# Сохраняем отфильтрованные задачи
output_file = "data/perplexity_tasks_filtered.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(filtered_tasks, f, ensure_ascii=False, indent=2)

print(f"\n💾 Сохранено в: {output_file}")
print(f"📊 Всего задач для импорта: {len(filtered_tasks)}")

# Статистика по разделам
from collections import Counter
subjects = Counter(t['subject'] for t in filtered_tasks)
print(f"\n📈 Распределение по разделам:")
for subject, count in subjects.most_common():
    print(f"  {subject}: {count} задач")

# Статистика по уровням
levels_count = Counter(t['difficulty'] for t in filtered_tasks)
print(f"\n📈 Распределение по уровням:")
for level in sorted(levels_count.keys()):
    print(f"  Уровень {level}: {levels_count[level]} задач")

print("\n" + "="*70)
print("✅ ГОТОВО!")
print("="*70)
print(f"\nФайл {output_file} готов к импорту в problems.py")
print(f"Всего задач: {len(filtered_tasks)}")
