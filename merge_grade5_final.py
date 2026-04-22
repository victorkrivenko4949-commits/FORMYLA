"""
Объединение основного файла и патча в финальную базу
"""

import json
from collections import Counter

# Читаем оба файла
tasks = []

# Основной файл
with open('grade5_olympiad_FINAL.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        tasks.append(json.loads(line))

# Патч
with open('grade5_olympiad_PATCH.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        tasks.append(json.loads(line))

print(f'Всего задач после объединения: {len(tasks)}')

# Проверка на дубликаты
keys = [(t['topic'], t['level'], t['step']) for t in tasks]
unique_keys = set(keys)
print(f'Уникальных задач: {len(unique_keys)}')
print(f'Дубликатов: {len(keys) - len(unique_keys)}')

# Удаляем дубликаты (оставляем первое вхождение)
seen = set()
unique_tasks = []
for task in tasks:
    key = (task['topic'], task['level'], task['step'])
    if key not in seen:
        seen.add(key)
        unique_tasks.append(task)

print(f'После удаления дубликатов: {len(unique_tasks)}')

# Сохраняем финальный файл
with open('grade5_olympiad_COMPLETE.jsonl', 'w', encoding='utf-8') as f:
    for task in unique_tasks:
        json.dump(task, f, ensure_ascii=False)
        f.write('\n')

print(f'\nФинальный файл: grade5_olympiad_COMPLETE.jsonl')

# Статистика
print('\n' + '='*70)
print('ФИНАЛЬНАЯ СТАТИСТИКА:')
print('='*70)

levels = Counter([t['level'] for t in unique_tasks])
print('\nПо уровням:')
for k in sorted(levels.keys()):
    expected = 10 * 15
    print(f'  Уровень {k}: {levels[k]}/{expected} ({levels[k]/expected*100:.0f}%)')

topics = Counter([t['topic'] for t in unique_tasks])
print('\nПо темам:')
for k, v in sorted(topics.items()):
    expected = 7 * 15
    print(f'  {k}: {v}/{expected} ({v/expected*100:.0f}%)')

# LaTeX статистика
latex_count = sum(1 for t in unique_tasks if '$' in t['question'] or '$' in t['explanation'])
print(f'\nЗадач с LaTeX: {latex_count}/{len(unique_tasks)} ({latex_count/len(unique_tasks)*100:.1f}%)')

print('\n' + '='*70)
print('ПРИМЕР ЗАДАЧИ 7-ГО УРОВНЯ С LATEX:')
print('='*70)

level_7 = [t for t in unique_tasks if t['level'] == 7 and '$' in t['explanation']]
if level_7:
    task = level_7[0]
    print(f'\nТема: {task["topic"]}')
    print(f'Уровень: {task["level"]}')
    print(f'\nВОПРОС:\n{task["question"][:400]}')
    print(f'\nОТВЕТ:\n{task["answer"]}')
    print(f'\nОБЪЯСНЕНИЕ (первые 500 символов):\n{task["explanation"][:500]}...')
