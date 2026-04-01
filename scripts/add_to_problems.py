# -*- coding: utf-8 -*-
"""
Добавление отфильтрованных задач из Perplexity в problems.py
"""
import sys
import os
import json
import codecs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

print("="*70)
print("Добавление задач в problems.py")
print("="*70)

# Читаем отфильтрованные задачи
input_file = "data/perplexity_tasks_filtered.json"
print(f"\n📄 Читаем: {input_file}")

with open(input_file, 'r', encoding='utf-8') as f:
    new_tasks = json.load(f)

print(f"✅ Загружено новых задач: {len(new_tasks)}")

# Читаем текущий problems.py
print(f"\n📄 Читаем текущий problems.py...")
with open('problems.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Находим PROBLEMS_DB
import_start = content.find('PROBLEMS_DB = [')
if import_start == -1:
    print("❌ Не найден PROBLEMS_DB в problems.py!")
    sys.exit(1)

# Находим последнюю задачу
last_brace = content.rfind('}', import_start)
if last_brace == -1:
    print("❌ Не найдена последняя задача!")
    sys.exit(1)

# Создаем строку с новыми задачами
new_tasks_str = ""
for task in new_tasks:
    new_tasks_str += ",\n{\n"
    new_tasks_str += f'"subject": "{task["subject"]}",\n'
    new_tasks_str += f'"subtopic": "{task["subtopic"]}",\n'
    new_tasks_str += f'"grade": {task["grade"]},\n'
    new_tasks_str += f'"difficulty": {task["difficulty"]},\n'
    new_tasks_str += f'"title": "{task["title"]}",\n'
    new_tasks_str += f'"text": "{task["text"]}",\n'
    new_tasks_str += f'"answer": "{task["answer"]}",\n'
    new_tasks_str += f'"solution": "{task["solution"]}",\n'
    new_tasks_str += f'"source": "{task["source"]}",\n'
    new_tasks_str += f'"source_dataset": "{task["source_dataset"]}",\n'
    new_tasks_str += f'"id": {task["id"]}\n'
    new_tasks_str += "}"

# Вставляем новые задачи
new_content = content[:last_brace+1] + new_tasks_str + content[last_brace+1:]

# Сохраняем
print(f"\n💾 Сохраняем обновленный problems.py...")
with open('problems.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"✅ Добавлено {len(new_tasks)} задач в problems.py")

# Проверяем
print(f"\n🔍 Проверка...")
from problems import PROBLEMS_DB
print(f"✅ Всего задач в базе: {len(PROBLEMS_DB)}")

levels = set(p.get('difficulty') for p in PROBLEMS_DB)
print(f"✅ Уровни в базе: {sorted(levels)}")

print("\n" + "="*70)
print("✅ ГОТОВО!")
print("="*70)
print(f"\nВ базе теперь {len(PROBLEMS_DB)} задач")
print(f"Добавлено: {len(new_tasks)} новых задач")
