"""
Анализ недостающих задач после первой генерации
"""

import json

# Загружаем эталоны и сгенерированные задачи
with open('adaptive_anchor_25_tasks_grade5_level3.json', 'r', encoding='utf-8') as f:
    anchors = json.load(f)

with open('adaptive_150_tasks_generated.json', 'r', encoding='utf-8') as f:
    generated = json.load(f)

# Целевые уровни (без 3, так как он уже есть в эталонах)
TARGET_LEVELS = [1, 2, 4, 5, 6, 7]

# Создаем словарь сгенерированных задач: {(topic, level): True}
generated_map = {}
for task in generated:
    key = (task['topic'], task['difficulty_level'])
    generated_map[key] = True

# Находим недостающие задачи
missing_tasks = []
for anchor in anchors:
    topic = anchor['topic']
    for level in TARGET_LEVELS:
        key = (topic, level)
        if key not in generated_map:
            missing_tasks.append({
                'topic': topic,
                'level': level,
                'anchor': anchor
            })

print("=" * 80)
print("ANALIZ NEDOSTAYUSHCHIKH ZADACH")
print("=" * 80)
print(f"Vsego dolzhno byt': 150 zadach (25 tem x 6 urovney)")
print(f"Sgenerirova no: {len(generated)} zadach")
print(f"Nedostayet: {len(missing_tasks)} zadach")
print()

# Группируем по темам
missing_by_topic = {}
for item in missing_tasks:
    topic = item['topic']
    if topic not in missing_by_topic:
        missing_by_topic[topic] = []
    missing_by_topic[topic].append(item['level'])

print("Недостающие задачи по темам:")
print("-" * 80)
for topic, levels in sorted(missing_by_topic.items()):
    print(f"{topic}: уровни {sorted(levels)}")

# Сохраняем список недостающих задач
with open('missing_tasks_list.json', 'w', encoding='utf-8') as f:
    json.dump(missing_tasks, f, ensure_ascii=False, indent=2)

print()
print("Spisok nedostayushchikh zadach sokhranyen v: missing_tasks_list.json")
print("=" * 80)
