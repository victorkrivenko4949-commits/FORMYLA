# -*- coding: utf-8 -*-
"""
Конвертация ВСЕХ задач в базе на уровни 1-5
Маппинг: 10,9 -> 5; 8,7 -> 4; 6,5 -> 3; 4,3 -> 2; 2,1 -> 1
"""
import sys
import os
import codecs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from problems import PROBLEMS_DB

print("="*70)
print("Конвертация всех задач на уровни 1-5")
print("="*70)

# Маппинг
LEVEL_MAP = {
    1: 1, 2: 1,
    3: 2, 4: 2,
    5: 3, 6: 3,
    7: 4, 8: 4,
    9: 5, 10: 5
}

print(f"\nВсего задач: {len(PROBLEMS_DB)}")

# Статистика ДО
from collections import Counter
before = Counter(p.get('difficulty', 0) for p in PROBLEMS_DB)
print(f"\nУровни ДО конвертации:")
for level in sorted(before.keys()):
    print(f"  Уровень {level}: {before[level]} задач")

# Конвертируем
for task in PROBLEMS_DB:
    old_level = task.get('difficulty', 1)
    new_level = LEVEL_MAP.get(old_level, old_level)
    task['difficulty'] = new_level

# Статистика ПОСЛЕ
after = Counter(p.get('difficulty') for p in PROBLEMS_DB)
print(f"\nУровни ПОСЛЕ конвертации:")
for level in sorted(after.keys()):
    print(f"  Уровень {level}: {after[level]} задач")

# Сохраняем
print(f"\nСохраняем обновленный problems.py...")

# Формируем содержимое
content = "# -*- coding: utf-8 -*-\n"
content += "# База задач — 5 уровней сложности\n\n"
content += "PROBLEMS_DB = [\n"

for i, task in enumerate(PROBLEMS_DB):
    if i > 0:
        content += ",\n"
    content += "{\n"
    content += f'"subject": "{task.get("subject", "")}",\n'
    content += f'"subtopic": "{task.get("subtopic", "")}",\n'
    content += f'"grade": {task.get("grade", 5)},\n'
    content += f'"difficulty": {task.get("difficulty", 1)},\n'
    
    # Экранируем спецсимволы
    title = str(task.get("title", "")).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    text = str(task.get("text", "")).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    answer = str(task.get("answer", "")).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    solution = str(task.get("solution", "")).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    
    content += f'"title": "{title}",\n'
    content += f'"text": "{text}",\n'
    content += f'"answer": "{answer}",\n'
    content += f'"solution": "{solution}",\n'
    content += f'"source": "{task.get("source", "Unknown")}",\n'
    content += f'"source_dataset": "{task.get("source_dataset", "unknown")}",\n'
    content += f'"id": {task.get("id", i+1)}\n'
    content += "}"

content += "\n]\n"

# Сохраняем
with open('problems.py', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"✅ Сохранено {len(PROBLEMS_DB)} задач")

print("\n" + "="*70)
print("✅ ГОТОВО!")
print("="*70)
print(f"\nВсего задач: {len(PROBLEMS_DB)}")
print(f"Уровни: 1-5")
