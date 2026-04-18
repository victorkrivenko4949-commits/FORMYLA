"""
Анализ недостающих задач для 6 класса
"""

import json

# Матрица тем для 6 класса
GRADE6_TOPICS = [
    "Дроби (сложение, вычитание, умножение, деление)",
    "Делимость чисел (НОД и НОК)",
    "Проценты и их применение",
    "Пропорции и отношения",
    "Модуль числа и координатная прямая",
    "Рыцари и Лжецы (сложные конструкции)",
    "Метод от противного",
    "Логические таблицы",
    "Принцип Дирихле",
    "Игры и стратегии",
    "Движение (по реке, навстречу, вдогонку)",
    "Совместная работа (производительность)",
    "Смеси и сплавы",
    "Метод обратного хода",
    "Переправы и взвешивания",
    "Правило суммы и произведения",
    "Перестановки",
    "Размещения и сочетания",
    "Подсчет вариантов (дерево)",
    "Графы (степени вершин)",
    "Площади и периметры сложных фигур",
    "Разрезания и замощения",
    "Углы и многоугольники",
    "Куб и его развертки",
    "Координатная плоскость"
]

# Загружаем якоря и сгенерированные задачи
with open('adaptive_anchor_25_tasks_grade6_level3.json', 'r', encoding='utf-8') as f:
    anchors = json.load(f)

with open('adaptive_175_grade6_COMPLETE.json', 'r', encoding='utf-8') as f:
    generated = json.load(f)

# Все уровни (включая 3 для якорей)
ALL_LEVELS = [1, 2, 3, 4, 5, 6, 7]

# Создаем словарь сгенерированных задач
generated_map = {}
for task in generated:
    key = (task['topic'], task['difficulty_level'])
    generated_map[key] = True

# Создаем словарь якорей
anchors_by_topic = {task['topic']: task for task in anchors}

# Находим недостающие задачи
missing_tasks = []
for topic in GRADE6_TOPICS:
    anchor = anchors_by_topic.get(topic)
    
    for level in ALL_LEVELS:
        key = (topic, level)
        if key not in generated_map:
            missing_tasks.append({
                'topic': topic,
                'level': level,
                'anchor': anchor if anchor else None
            })

print("=" * 80)
print("ANALIZ NEDOSTAYUSHCHIKH ZADACH (Grade 6)")
print("=" * 80)
print(f"Total should be: 175 tasks (25 topics x 7 levels)")
print(f"Generated: {len(generated)} tasks")
print(f"Missing: {len(missing_tasks)} tasks")
print()

# Группируем по темам
missing_by_topic = {}
for item in missing_tasks:
    topic = item['topic']
    if topic not in missing_by_topic:
        missing_by_topic[topic] = []
    missing_by_topic[topic].append(item['level'])

print("Missing tasks by topic:")
print("-" * 80)
for topic, levels in sorted(missing_by_topic.items()):
    print(f"{topic}: levels {sorted(levels)}")

# Сохраняем список недостающих задач
with open('missing_tasks_grade6.json', 'w', encoding='utf-8') as f:
    json.dump(missing_tasks, f, ensure_ascii=False, indent=2)

print()
print(f"Saved to: missing_tasks_grade6.json")
print("=" * 80)
