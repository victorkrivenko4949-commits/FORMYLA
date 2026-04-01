# -*- coding: utf-8 -*-
"""
Быстрое добавление задач из problems_67.py
"""
import sys
import codecs

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

print("Читаем problems_67.py...")
exec(open('problems_67.py', encoding='utf-8').read())
tasks_67 = PROBLEMS_DB.copy()
print(f"Задач из problems_67.py: {len(tasks_67)}")

print("Читаем problems.py...")
exec(open('problems.py', encoding='utf-8').read())
current = PROBLEMS_DB.copy()
print(f"Задач в problems.py: {len(current)}")

# Обновляем ID
max_id = max(t['id'] for t in current)
for i, t in enumerate(tasks_67):
    t['id'] = max_id + i + 1

print(f"\nДобавляем {len(tasks_67)} задач...")

# Читаем файл
with open('problems.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Находим последнюю закрывающую скобку
last_bracket = content.rfind(']')

# Формируем строку с новыми задачами
import json
tasks_str = ',\n'.join([json.dumps(t, ensure_ascii=False) for t in tasks_67])

# Вставляем
new_content = content[:last_bracket] + ',\n' + tasks_str + '\n' + content[last_bracket:]

# Сохраняем
print("Сохраняем...")
with open('problems.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"✅ Готово! Всего задач: {len(current) + len(tasks_67)}")
