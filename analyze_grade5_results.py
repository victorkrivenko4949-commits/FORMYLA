import json
from collections import Counter

tasks = [json.loads(line) for line in open('grade5_olympiad_FINAL.jsonl', encoding='utf-8')]

print(f'Всего задач: {len(tasks)} из 1050')
print(f'Успешность: {len(tasks)/1050*100:.1f}%\n')

print('По уровням:')
levels = Counter([t['level'] for t in tasks])
for k in sorted(levels.keys()):
    expected = 10 * 15  # 10 тем * 15 задач
    print(f'  Уровень {k}: {levels[k]}/{expected} ({levels[k]/expected*100:.0f}%)')

print('\nПо темам:')
topics = Counter([t['topic'] for t in tasks])
for k, v in sorted(topics.items()):
    expected = 7 * 15  # 7 уровней * 15 задач
    print(f'  {k}: {v}/{expected} ({v/expected*100:.0f}%)')

print('\n' + '='*70)
print('ПРИМЕРЫ ЗАДАЧ С LATEX:')
print('='*70)

# Ищем задачи с LaTeX (содержат $)
latex_tasks = [t for t in tasks if '$' in t['question'] or '$' in t['explanation']]
print(f'\nЗадач с LaTeX: {len(latex_tasks)} из {len(tasks)} ({len(latex_tasks)/len(tasks)*100:.1f}%)\n')

if latex_tasks:
    # Показываем 2 примера
    for i, task in enumerate(latex_tasks[:2], 1):
        print(f'\n--- ПРИМЕР {i} ---')
        print(f'Тема: {task["topic"]}')
        print(f'Уровень: {task["level"]}')
        print(f'\nВОПРОС:\n{task["question"][:300]}...')
        print(f'\nОТВЕТ:\n{task["answer"]}')
        print(f'\nОБЪЯСНЕНИЕ (первые 400 символов):\n{task["explanation"][:400]}...')
        print('='*70)
