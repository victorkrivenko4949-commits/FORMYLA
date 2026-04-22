import json
from collections import Counter

tasks = [json.loads(line) for line in open('grade5_olympiad_PERFECT.jsonl', encoding='utf-8')]

print(f'Задач в PERFECT файле: {len(tasks)}')
print(f'Нужно догенерировать: {1050 - len(tasks)} задач')

print('\nПо уровням:')
levels = Counter([t['level'] for t in tasks])
for k in sorted(levels.keys()):
    print(f'  Уровень {k}: {levels[k]}')

print('\nПо темам:')
topics = Counter([t['topic'] for t in tasks])
for k, v in sorted(topics.items()):
    print(f'  {k[:40]}: {v}')

long = [t for t in tasks if len(t['answer']) > 50]
print(f'\nДлинных ответов (>50): {len(long)}')

latex = sum(1 for t in tasks if '$' in t['question'] or '$' in t['explanation'])
print(f'Задач с LaTeX: {latex} ({latex/len(tasks)*100:.1f}%)')

# Проверка юникода
forbidden = ['×', '÷', '≈', '≤', '≥', '²', '³', '½', '°']
unicode_count = 0
for task in tasks:
    text = task['question'] + task['explanation']
    if any(char in text for char in forbidden):
        unicode_count += 1

print(f'Задач с юникод-символами: {unicode_count}')

print('\n' + '='*70)
if len(tasks) == 1050 and unicode_count == 0 and len(long) < 50:
    print('[OK] БАЗА ИДЕАЛЬНА!')
else:
    print(f'[INFO] Нужно догенерировать {1050-len(tasks)} задач')
