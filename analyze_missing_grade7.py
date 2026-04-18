"""
Анализ недостающих задач для 7 класса
"""

import json

GRADE7_TOPICS = [
    "Вычисления (рациональные числа)",
    "Движение (вдогонку и навстречу)",
    "Совместная работа",
    "Проценты",
    "Делимость (признаки)",
    "НОД и НОК",
    "Простые и составные числа",
    "Уравнения (текстовые)",
    "Линейные диофантовы уравнения",
    "Логика (Рыцари и лжецы)",
    "Принцип Дирихле)",
    "Метод от противного",
    "Инварианты (четность)",
    "Инварианты (раскраски)",
    "Игры (симметрия)",
    "Игры (анализ с конца)",
    "Графы (степени вершин)",
    "Графы (связность)",
    "Геометрия (смежные и вертикальные углы)",
    "Геометрия (равнобедренный треугольник)",
    "Комбинаторика (правило умножения)",
    "Комбинаторика (перестановки)",
    "Текстовые задачи на возраст",
    "Взвешивания",
    "Закономерности"
]

with open('adaptive_175_grade7_COMPLETE.json', 'r', encoding='utf-8') as f:
    generated = json.load(f)

with open('adaptive_anchor_25_tasks_grade7_level3.json', 'r', encoding='utf-8') as f:
    anchors = json.load(f)

ALL_LEVELS = [1, 2, 3, 4, 5, 6, 7]

generated_map = {}
for task in generated:
    key = (task['topic'], task['difficulty_level'])
    generated_map[key] = True

anchors_by_topic = {task['topic']: task for task in anchors}

missing_tasks = []
for topic in GRADE7_TOPICS:
    anchor = anchors_by_topic.get(topic)
    
    for level in ALL_LEVELS:
        key = (topic, level)
        if key not in generated_map:
            missing_tasks.append({
                'topic': topic,
                'level': level,
                'anchor': anchor
            })

print("=" * 80)
print("MISSING TASKS ANALYSIS (Grade 7)")
print("=" * 80)
print(f"Total should be: 175 tasks")
print(f"Generated: {len(generated)} tasks")
print(f"Missing: {len(missing_tasks)} tasks")
print()

missing_by_topic = {}
for item in missing_tasks:
    topic = item['topic']
    if topic not in missing_by_topic:
        missing_by_topic[topic] = []
    missing_by_topic[topic].append(item['level'])

print("Missing by topic:")
for topic, levels in sorted(missing_by_topic.items()):
    print(f"  {topic}: levels {sorted(levels)}")

with open('missing_tasks_grade7.json', 'w', encoding='utf-8') as f:
    json.dump(missing_tasks, f, ensure_ascii=False, indent=2)

print()
print(f"Saved to: missing_tasks_grade7.json")
print("=" * 80)
