# -*- coding: utf-8 -*-
"""
Переназначение уровней 1-10 на 1-5 для задач от Perplexity
Маппинг: 10,9 -> 5; 8,7 -> 4; 6,5 -> 3; 4,3 -> 2; 2,1 -> 1
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
print("Переназначение уровней 1-10 на 1-5")
print("="*70)

# Маппинг уровней
LEVEL_MAPPING = {
    1: 1,
    2: 1,
    3: 2,
    4: 2,
    5: 3,
    6: 3,
    7: 4,
    8: 4,
    9: 5,
    10: 5
}

print(f"\n📋 Маппинг уровней:")
for old, new in LEVEL_MAPPING.items():
    print(f"  {old} -> {new}")

# Читаем файл от Perplexity
input_file = "../../Downloads/all_2285_tasks (1).json"
print(f"\n📄 Читаем файл: {input_file}")

with open(input_file, 'r', encoding='utf-8') as f:
    perplexity_tasks = json.load(f)

print(f"✅ Загружено задач: {len(perplexity_tasks)}")

# Получаем максимальный ID из текущей базы
max_id = max(p.get('id', 0) for p in PROBLEMS_DB) if PROBLEMS_DB else 0
print(f"\n🆔 Максимальный ID в базе: {max_id}")

# Переназначаем уровни и ID
next_id = max_id + 1
for i, task in enumerate(perplexity_tasks):
    old_level = task.get('difficulty', 1)
    new_level = LEVEL_MAPPING.get(old_level, 1)
    task['difficulty'] = new_level
    task['id'] = next_id + i

print(f"🆔 Новые ID: {next_id} - {next_id + len(perplexity_tasks) - 1}")

# Статистика по уровням
from collections import Counter
levels_before = Counter(LEVEL_MAPPING.keys())
levels_after = Counter(t['difficulty'] for t in perplexity_tasks)

print(f"\n📈 Распределение по уровням ПОСЛЕ переназначения:")
for level in sorted(levels_after.keys()):
    print(f"  Уровень {level}: {levels_after[level]} задач")

# Сохраняем
output_file = "data/perplexity_tasks_remapped.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(perplexity_tasks, f, ensure_ascii=False, indent=2)

print(f"\n💾 Сохранено в: {output_file}")
print(f"📊 Всего задач: {len(perplexity_tasks)}")

# Статистика по разделам
subjects = Counter(t['subject'] for t in perplexity_tasks)
print(f"\n📈 Распределение по разделам:")
for subject, count in subjects.most_common():
    print(f"  {subject}: {count} задач")

print("\n" + "="*70)
print("✅ ГОТОВО!")
print("="*70)
print(f"\nФайл {output_file} готов к импорту")
print(f"Всего задач: {len(perplexity_tasks)}")
print(f"Уровни: 1-5 (переназначены из 1-10)")
