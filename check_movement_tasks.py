import json

with open('data/adaptive_full_db.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Ищем задачи на движение
movement_tasks = [t for t in data if 'движен' in t['topic'].lower()]
print(f"Задач на движение: {len(movement_tasks)}")

if movement_tasks:
    print("\nПримеры тем:")
    for task in movement_tasks[:5]:
        print(f"  - {task['topic']}")
else:
    print("\n❌ Задач на движение НЕТ в базе данных!")
    print("\nВсе уникальные темы в БД:")
    all_topics = sorted(set(t['topic'] for t in data))
    for topic in all_topics:
        print(f"  - {topic}")
