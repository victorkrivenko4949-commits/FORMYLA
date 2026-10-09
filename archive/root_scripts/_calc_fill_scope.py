#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Calculate exactly how many tasks are missing per cell for L1 and L2,
and determine the optimal filling plan with diversity constraints.
"""
import json
from collections import defaultdict

DB_PATH = 'adaptive_data/adaptive_full_9120_fixed.json'

with open(DB_PATH, 'r', encoding='utf-8') as f:
    db = json.load(f)

l1 = [t for t in db if t.get('level') == 1]
l2 = [t for t in db if t.get('level') == 2]

TARGET = 5

def analyze_holes(tasks, level_name):
    """Analyze holes by (grade, topic) and (grade, section)."""
    by_topic = defaultdict(list)
    by_section = defaultdict(list)
    
    for t in tasks:
        grade = t.get('grade', '?')
        topic = t.get('topic', '')
        section = t.get('section', '')
        by_topic[(grade, topic)].append(t)
        by_section[(grade, section)].append(t)
    
    print(f"\n{'='*60}")
    print(f"  {level_name} — Анализ дыр для заполнения")
    print(f"{'='*60}")
    
    for cell_type, cells, label in [
        ("(grade, topic)", by_topic, "Темам"),
        ("(grade, section)", by_section, "Разделам")
    ]:
        holes = {k: v for k, v in cells.items() if len(v) < TARGET}
        full = {k: v for k, v in cells.items() if len(v) == TARGET}
        over = {k: v for k, v in cells.items() if len(v) > TARGET}
        
        total_missing = sum(TARGET - len(v) for v in holes.values())
        
        # Count by how many tasks are needed
        need_1 = sum(1 for v in holes.values() if len(v) == 4)
        need_2 = sum(1 for v in holes.values() if len(v) == 3)
        need_3 = sum(1 for v in holes.values() if len(v) == 2)
        need_4 = sum(1 for v in holes.values() if len(v) == 1)
        need_5 = sum(1 for v in holes.values() if len(v) == 0)
        
        print(f"\n  По {label} (type={cell_type}):")
        print(f"    Всего ячеек: {len(cells)}")
        print(f"    Полных (={TARGET}): {len(full)}")
        print(f"    Переполнено (>{TARGET}): {len(over)} — всего задач: {sum(len(v) for v in over.values())}")
        print(f"    Дыр (<{TARGET}): {len(holes)} — не хватает задач: {total_missing}")
        print(f"    Из них:")
        print(f"      Нужно 1 задачу (есть 4): {need_1}")
        print(f"      Нужно 2 задачи (есть 3): {need_2}")
        print(f"      Нужно 3 задачи (есть 2): {need_3}")
        print(f"      Нужно 4 задачи (есть 1): {need_4}")
        print(f"      Пустых (нужно 5): {need_5}")
        
        # Show smallest holes first (most urgent)
        if cell_type == "(grade, section)":
            print(f"\n    Первые 10 самых критичных дыр (по разделам):")
            sorted_holes = sorted(holes.items(), key=lambda x: len(x[1]))
            for (grade, topic_or_section), tasks in sorted_holes[:10]:
                print(f"      {level_name} | {grade} | {topic_or_section} — {len(tasks)}/{TARGET} (не хватает {TARGET - len(tasks)})")

analyze_holes(l1, "L1")
analyze_holes(l2, "L2")

# Also calculate total across both levels
print(f"\n{'='*60}")
print(f"  СВОДКА: СКОЛЬКО ВСЕГО НУЖНО СГЕНЕРИРОВАТЬ")
print(f"{'='*60}")

total_by_topic_missing = 0
total_by_section_missing = 0

for level_name, tasks in [("L1", l1), ("L2", l2)]:
    by_topic = defaultdict(list)
    by_section = defaultdict(list)
    for t in tasks:
        by_topic[(t.get('grade'), t.get('topic'))].append(t)
        by_section[(t.get('grade'), t.get('section'))].append(t)
    
    topic_holes = {k: v for k, v in by_topic.items() if len(v) < TARGET}
    section_holes = {k: v for k, v in by_section.items() if len(v) < TARGET}
    
    topic_missing = sum(TARGET - len(v) for v in topic_holes.values())
    section_missing = sum(TARGET - len(v) for v in section_holes.values())
    total_by_topic_missing += topic_missing
    total_by_section_missing += section_missing
    
    print(f"  {level_name}:")
    print(f"    По темам (topic): нужно {topic_missing} задач в {len(topic_holes)} ячейках")
    print(f"    По разделам (section): нужно {section_missing} задач в {len(section_holes)} ячейках")

print(f"\n  ВСЕГО по темам: {total_by_topic_missing} задач")
print(f"  ВСЕГО по разделам: {total_by_section_missing} задач")
