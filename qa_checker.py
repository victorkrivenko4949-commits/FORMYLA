"""
QA Валидатор для проверки качества олимпиадных задач
Проверяет LaTeX, длину ответов, дубликаты и баланс
"""

import json
import re
from collections import Counter

# Читаем файл
tasks = []
with open('grade5_olympiad_COMPLETE.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        tasks.append(json.loads(line))

print("="*70)
print(f"QA ПРОВЕРКА: {len(tasks)} ЗАДАЧ")
print("="*70)

# ПРАВИЛО 1: Проверка LaTeX
print("\n[1] ПРОВЕРКА LATEX:")
print("-"*70)

# Запрещенные юникод-символы
forbidden_unicode = ['²', '³', '½', '¼', '¾', '°', '×', '÷', '≤', '≥', '≠', '≈', '∞', '√', '∑', '∏', '∫', '⌈', '⌉', '⌊', '⌋']
forbidden_words = ['кв. см', 'куб. см', 'градусов', 'кв.см', 'куб.см']

unicode_violations = []
word_violations = []

for task in tasks:
    text = task['question'] + ' ' + task['explanation']
    
    # Проверка юникод-символов
    for symbol in forbidden_unicode:
        if symbol in text:
            unicode_violations.append({
                'task': f"{task['topic'][:30]} L{task['level']} S{task['step']}",
                'symbol': symbol,
                'question': task['question'][:100]
            })
            break
    
    # Проверка запрещенных слов
    for word in forbidden_words:
        if word in text.lower():
            word_violations.append({
                'task': f"{task['topic'][:30]} L{task['level']} S{task['step']}",
                'word': word,
                'question': task['question'][:100]
            })
            break

print(f"Задач с юникод-символами: {len(unicode_violations)}")
if unicode_violations:
    print("\nПримеры:")
    for v in unicode_violations[:3]:
        symbol_code = ord(v['symbol'])
        print(f"  - {v['task']}: символ U+{symbol_code:04X}")
        print(f"    Вопрос: {v['question']}...")

print(f"\nЗадач с запрещенными словами: {len(word_violations)}")
if word_violations:
    print("\nПримеры:")
    for v in word_violations[:3]:
        print(f"  - {v['task']}: слово '{v['word']}'")

# ПРАВИЛО 2: Проверка длины ответов
print("\n[2] ПРОВЕРКА ДЛИНЫ ОТВЕТОВ:")
print("-"*70)

long_answers = []
for task in tasks:
    answer_len = len(task['answer'])
    if answer_len > 50:
        long_answers.append({
            'task': f"{task['topic'][:30]} L{task['level']} S{task['step']}",
            'length': answer_len,
            'answer': task['answer']
        })

print(f"Задач с длинным ответом (>50 символов): {len(long_answers)}")
if long_answers:
    print("\nПримеры:")
    for v in sorted(long_answers, key=lambda x: x['length'], reverse=True)[:5]:
        print(f"  - {v['task']}: {v['length']} символов")
        print(f"    Ответ: {v['answer'][:80]}...")

# ПРАВИЛО 3: Проверка дубликатов
print("\n[3] ПРОВЕРКА ДУБЛИКАТОВ:")
print("-"*70)

questions = [task['question'] for task in tasks]
question_counts = Counter(questions)
duplicates = {q: count for q, count in question_counts.items() if count > 1}

print(f"Точных дубликатов вопросов: {len(duplicates)}")
if duplicates:
    print("\nПримеры:")
    for q, count in list(duplicates.items())[:3]:
        print(f"  - Повторяется {count} раз: {q[:100]}...")

# ПРАВИЛО 4: Баланс уровней
print("\n[4] БАЛАНС ПО УРОВНЯМ:")
print("-"*70)

levels = Counter([task['level'] for task in tasks])
for level in range(1, 8):
    count = levels[level]
    expected = 150
    status = "[OK]" if count == expected else "[FAIL]"
    print(f"  Уровень {level}: {count}/{expected} {status}")

# ПРАВИЛО 5: Баланс по темам
print("\n[5] БАЛАНС ПО ТЕМАМ:")
print("-"*70)

topics = Counter([task['topic'] for task in tasks])
for topic in sorted(topics.keys()):
    count = topics[topic]
    expected = 105
    status = "[OK]" if count == expected else "[FAIL]"
    print(f"  {topic[:40]:40} {count}/{expected} {status}")

# ИТОГОВЫЙ ОТЧЕТ
print("\n" + "="*70)
print("ИТОГОВЫЙ ОТЧЕТ:")
print("="*70)

total_issues = len(unicode_violations) + len(word_violations) + len(long_answers) + len(duplicates)
print(f"Всего задач: {len(tasks)}")
print(f"Задач с проблемами: {total_issues}")
print(f"Качество: {(len(tasks)-total_issues)/len(tasks)*100:.1f}%")

if total_issues == 0:
    print("\n[OK] ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ! База готова к использованию.")
else:
    print(f"\n[WARN] Найдено {total_issues} задач с проблемами. Рекомендуется исправить или перегенерировать.")
