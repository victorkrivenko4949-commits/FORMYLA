# -*- coding: utf-8 -*-
"""
Добавление переназначенных задач в problems.py
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
print("Добавление задач в problems.py")
print("="*70)

# Читаем переназначенные задачи
input_file = "data/perplexity_tasks_remapped.json"
print(f"\nЧитаем: {input_file}")

with open(input_file, 'r', encoding='utf-8') as f:
    new_tasks = json.load(f)

print(f"Новых задач: {len(new_tasks)}")
print(f"Текущих задач: {len(PROBLEMS_DB)}")
print(f"Будет всего: {len(PROBLEMS_DB) + len(new_tasks)}")

# Читаем problems.py
with open('problems.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Находим последнюю закрывающую скобку списка
last_bracket = content.rfind(']')
if last_bracket == -1:
    print("Ошибка: не найден конец PROBLEMS_DB")
    sys.exit(1)

# Формируем строку с новыми задачами
tasks_lines = []
for task in new_tasks:
    task_str = "{\n"
    task_str += f'"subject": "{task["subject"]}",\n'
    task_str += f'"subtopic": "{task["subtopic"]}",\n'
    task_str += f'"grade": {task["grade"]},\n'
    task_str += f'"difficulty": {task["difficulty"]},\n'
    task_str += f'"title": "{task["title"]}",\n'
    # Экранируем кавычки в тексте
    text = task["text"].replace('"', '\\"')
    answer = task["answer"].replace('"', '\\"')
    solution = task["solution"].replace('"', '\\"')
    task_str += f'"text": "{text}",\n'
    task_str += f'"answer": "{answer}",\n'
    task_str += f'"solution": "{solution}",\n'
    task_str += f'"source": "{task["source"]}",\n'
    task_str += f'"source_dataset": "{task["source_dataset"]}",\n'
    task_str += f'"id": {task["id"]}\n'
    task_str += "}"
    tasks_lines.append(task_str)

# Объединяем задачи
new_tasks_str = ",\n".join(tasks_lines)

# Вставляем перед закрывающей скобкой
new_content = content[:last_bracket] + ",\n" + new_tasks_str + "\n" + content[last_bracket:]

# Сохраняем
print(f"\nСохраняем обновленный problems.py...")
with open('problems.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"Готово! Добавлено {len(new_tasks)} задач")

print("\n" + "="*70)
print("ЗАВЕРШЕНО")
print("="*70)
print(f"\nВсего задач в базе: {len(PROBLEMS_DB) + len(new_tasks)}")
