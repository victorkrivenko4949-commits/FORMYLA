"""
Анализ недостающих задач для 8-11 классов
"""

import json
import os
from collections import defaultdict

ANCHOR_FILES = {
    8: "anchor_grade8.json",
    9: "anchor_grade9.json",
    10: "grade10_anchor.json",
    11: "grade11_anchor.json"
}

DIFFICULTY_LEVELS = [1, 2, 4, 5, 6, 7]

for grade in [8, 9, 10, 11]:
    print(f"\n{'='*80}")
    print(f"КЛАСС {grade}")
    print(f"{'='*80}")
    
    # Загружаем якорные задачи
    with open(ANCHOR_FILES[grade], 'r', encoding='utf-8') as f:
        anchors = json.load(f)
    
    topics = [task["topic"] for task in anchors]
    
    # Загружаем сгенерированные задачи
    generated_file = f"adaptive_150_tasks_grade{grade}_FINAL.json"
    if not os.path.exists(generated_file):
        generated_file = f"adaptive_150_tasks_grade{grade}_MERGED.json"
    if not os.path.exists(generated_file):
        generated_file = f"adaptive_150_tasks_grade{grade}_COMPLETE.json"
    if not os.path.exists(generated_file):
        generated_file = f"adaptive_150_tasks_grade{grade}.json"
    try:
        with open(generated_file, 'r', encoding='utf-8') as f:
            generated = json.load(f)
    except FileNotFoundError:
        print(f"Файл {generated_file} не найден!")
        continue
    
    print(f"Сгенерировано: {len(generated)}/150 задач")
    
    # Группируем по темам и уровням
    existing = defaultdict(set)
    for task in generated:
        topic = task["topic"]
        level = task["difficulty_level"]
        existing[topic].add(level)
    
    # Находим недостающие
    missing = []
    for topic in topics:
        for level in DIFFICULTY_LEVELS:
            if level not in existing[topic]:
                missing.append((topic, level))
    
    print(f"Недостающих задач: {len(missing)}")
    
    if missing:
        print(f"\nСписок недостающих задач:")
        by_topic = defaultdict(list)
        for topic, level in missing:
            by_topic[topic].append(level)
        
        for topic in sorted(by_topic.keys()):
            levels = sorted(by_topic[topic])
            print(f"  {topic}: уровни {levels}")
        
        # Сохраняем список недостающих
        missing_data = []
        for topic, level in missing:
            # Находим якорную задачу для этой темы
            anchor = next((t for t in anchors if t["topic"] == topic), None)
            if anchor:
                missing_data.append({
                    "grade": grade,
                    "topic": topic,
                    "level": level,
                    "anchor": anchor
                })
        
        output_file = f"missing_tasks_grade{grade}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(missing_data, f, ensure_ascii=False, indent=2)
        
        print(f"\nСохранено в {output_file}")

print(f"\n{'='*80}")
print("АНАЛИЗ ЗАВЕРШЕН")
print(f"{'='*80}\n")
