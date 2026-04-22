import json
from collections import Counter

tasks = [json.loads(line) for line in open('grade5_olympiad_tasks.jsonl', encoding='utf-8')]

print(f'Всего задач: {len(tasks)}')
print('\nПо уровням:')
levels = Counter([t['level'] for t in tasks])
for k in sorted(levels.keys()):
    print(f'  Уровень {k}: {levels[k]}')

print('\nПо темам:')
topics = Counter([t['topic'] for t in tasks])
for k, v in topics.items():
    print(f'  {k}: {v}')

print('\n' + '='*60)
print('ПРИМЕР ЗАДАЧИ 7-ГО УРОВНЯ:')
print('='*60)

level_7 = [t for t in tasks if t['level'] == 7]
if level_7:
    task = level_7[0]
    print(f'\nТема: {task["topic"]}')
    print(f'Уровень: {task["level"]}')
    print(f'\nВОПРОС:\n{task["question"]}')
    print(f'\nОТВЕТ:\n{task["answer"]}')
    print(f'\nОБЪЯСНЕНИЕ:\n{task["explanation"][:500]}...')
else:
    print('\nЗадачи 7-го уровня не найдены!')
