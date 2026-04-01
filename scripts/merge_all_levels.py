# -*- coding: utf-8 -*-
"""
Объединение всех файлов задач в один с 7 уровнями
"""
import sys
import codecs

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

print("="*70)
print("Объединение задач из всех файлов")
print("="*70)

# Читаем текущий problems.py
exec(open('problems.py', encoding='utf-8').read())
current_tasks = PROBLEMS_DB.copy()
print(f"\n📄 problems.py: {len(current_tasks)} задач")

# Читаем problems_67.py
exec(open('problems_67.py', encoding='utf-8').read())
tasks_67 = PROBLEMS_DB.copy()
print(f"📄 problems_67.py: {len(tasks_67)} задач")

# Объединяем
all_tasks = current_tasks + tasks_67

# Обновляем ID
for i, task in enumerate(all_tasks, 1):
    task['id'] = i

print(f"\n✅ Всего задач после объединения: {len(all_tasks)}")

# Статистика по уровням
from collections import Counter
levels = Counter(t.get('difficulty') for t in all_tasks)
print(f"\n📊 Распределение по уровням:")
for level in sorted(levels.keys()):
    print(f"  Уровень {level}: {levels[level]} задач")

# Сохраняем
print(f"\n💾 Сохраняем в problems.py...")

content = "# -*- coding: utf-8 -*-\n"
content += f"# База задач FORMYLA - {len(all_tasks)} задач, 7 уровней\n\n"
content += "PROBLEMS_DB = [\n"

for i, task in enumerate(all_tasks):
    if i > 0:
        content += ",\n"
    content += "{\n"
    for key in ['subject', 'subtopic', 'grade', 'difficulty', 'title', 'text', 'answer', 'solution', 'source', 'source_dataset', 'id']:
        value = task.get(key, '')
        if key in ['grade', 'difficulty', 'id']:
            content += f'"{key}": {value},\n'
        else:
            # Экранируем
            val_str = str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            content += f'"{key}": "{val_str}",\n'
    content = content.rstrip(',\n') + '\n'
    content += "}"

content += "\n]\n"

with open('problems.py', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"✅ Сохранено!")

print("\n" + "="*70)
print("✅ ГОТОВО!")
print("="*70)
print(f"\nВсего задач: {len(all_tasks)}")
print(f"Уровни: 1-7")
