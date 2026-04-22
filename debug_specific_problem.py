"""
Скрипт для поиска конкретной задачи в базе данных
"""

try:
    from problems import PROBLEMS_DB
except ImportError:
    PROBLEMS_DB = []

try:
    from adaptive_data import ADAPTIVE_DB
except ImportError:
    ADAPTIVE_DB = []

# Ищем задачу с текстом "x + 5 = 12" или похожим
search_text = "x + 5 = 12"

print("=" * 70)
print("ПОИСК ЗАДАЧИ В БАЗЕ ДАННЫХ")
print("=" * 70)
print(f"Ищем задачу содержащую: '{search_text}'")
print()

found_count = 0

# Поиск в PROBLEMS_DB
print("Поиск в PROBLEMS_DB...")
for problem in PROBLEMS_DB:
    text = problem.get('text', '') or problem.get('title', '')
    if 'x' in text.lower() and '5' in text and '12' in text:
        found_count += 1
        print(f"\n[НАЙДЕНО #{found_count}] ID: {problem.get('id')}")
        print(f"Текст: {text[:100]}...")
        print(f"Ответ в БД: '{problem.get('answer')}'")
        print(f"Тип ответа: {type(problem.get('answer'))}")
        print(f"Класс: {problem.get('grade')}, Сложность: {problem.get('difficulty')}")

# Поиск в ADAPTIVE_DB
print("\n" + "=" * 70)
print("Поиск в ADAPTIVE_DB...")
for task in ADAPTIVE_DB:
    text = task.get('text', '') or task.get('title', '')
    if 'x' in text.lower() and '5' in text and '12' in text:
        found_count += 1
        print(f"\n[НАЙДЕНО #{found_count}] ID: {task.get('id')}")
        print(f"Текст: {text[:100]}...")
        print(f"Ответ в БД: '{task.get('answer')}'")
        print(f"Тип ответа: {type(task.get('answer'))}")
        print(f"Класс: {task.get('class_level')}, Тема: {task.get('topic')}")

print("\n" + "=" * 70)
print(f"Всего найдено задач: {found_count}")
print("=" * 70)

if found_count == 0:
    print("\nЗадача не найдена. Попробуем более широкий поиск...")
    print("\nПервые 5 задач из PROBLEMS_DB:")
    for i, p in enumerate(PROBLEMS_DB[:5], 1):
        print(f"\n{i}. ID: {p.get('id')}")
        print(f"   Текст: {str(p.get('text', p.get('title', '')))[:80]}...")
        print(f"   Ответ: '{p.get('answer')}'")
    
    print("\nПервые 5 задач из ADAPTIVE_DB:")
    for i, t in enumerate(ADAPTIVE_DB[:5], 1):
        print(f"\n{i}. ID: {t.get('id')}")
        print(f"   Текст: {str(t.get('text', t.get('title', '')))[:80]}...")
        print(f"   Ответ: '{t.get('answer')}'")
