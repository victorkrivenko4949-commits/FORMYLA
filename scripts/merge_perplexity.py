# -*- coding: utf-8 -*-
"""
Объединение задач из Perplexity с текущей базой
"""
import sys
import os
import json
import codecs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

print("="*70)
print("Объединение задач Perplexity с базой")
print("="*70)

# Читаем переназначенные задачи
with open('data/perplexity_tasks_remapped.json', 'r', encoding='utf-8') as f:
    new_tasks = json.load(f)

print(f"\nНовых задач: {len(new_tasks)}")

# Читаем текущий problems.py
with open('problems.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Находим конец PROBLEMS_DB
end_index = -1
for i in range(len(lines) - 1, -1, -1):
    if ']' in lines[i] and 'PROBLEMS_DB' not in lines[i]:
        end_index = i
        break

if end_index == -1:
    print("Ошибка: не найден конец PROBLEMS_DB")
    sys.exit(1)

print(f"Найден конец списка на строке {end_index + 1}")

# Формируем новые задачи в формате Python
new_lines = []
for task in new_tasks:
    new_lines.append(",\n{\n")
    new_lines.append(f'"subject": "{task["subject"]}",\n')
    new_lines.append(f'"subtopic": "{task["subtopic"]}",\n')
    new_lines.append(f'"grade": {task["grade"]},\n')
    new_lines.append(f'"difficulty": {task["difficulty"]},\n')
    # Экранируем спецсимволы
    title = task["title"].replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    text = task["text"].replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    answer = task["answer"].replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    solution = task["solution"].replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    new_lines.append(f'"title": "{title}",\n')
    new_lines.append(f'"text": "{text}",\n')
    new_lines.append(f'"answer": "{answer}",\n')
    new_lines.append(f'"solution": "{solution}",\n')
    new_lines.append(f'"source": "{task["source"]}",\n')
    new_lines.append(f'"source_dataset": "{task["source_dataset"]}",\n')
    new_lines.append(f'"id": {task["id"]}\n')
    new_lines.append("}\n")

# Вставляем новые задачи перед закрывающей скобкой
new_content = lines[:end_index] + new_lines + lines[end_index:]

# Сохраняем
print(f"\nСохраняем обновленный problems.py...")
with open('problems.py', 'w', encoding='utf-8') as f:
    f.writelines(new_content)

print(f"✅ Добавлено {len(new_tasks)} задач")

print("\n" + "="*70)
print("ЗАВЕРШЕНО")
print("="*70)
