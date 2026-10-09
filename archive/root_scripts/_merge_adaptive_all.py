#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Объединяет final_db_1_5.json (уровни 1-5) + gen_678/ задачи (уровни 6-8)
в один файл adaptive_all_1_8.json
"""
import json, os, sys, glob

BASE = os.path.dirname(os.path.abspath(__file__))

# 1. Загружаем final_db_1_5 (уровни 1-5)
FINAL_DB = r"C:\Users\Victor\Downloads\final_db_1_5.json"
print(f"Loading {FINAL_DB}...")
with open(FINAL_DB, 'r', encoding='utf-8') as f:
    db15 = json.load(f)
print(f"  Level 1-5 tasks: {len(db15)}")

# 2. Загружаем gen_678 задачи (уровни 6-8)
dirs_678 = [
    os.path.join(BASE, 'gen_678', 'L6'),
    os.path.join(BASE, 'gen_678', 'L7'),
    os.path.join(BASE, 'gen_678', 'L8'),
    os.path.join(BASE, 'gen_678', 'reserve'),
]
tasks_678 = []
for d in dirs_678:
    if not os.path.isdir(d):
        print(f"  WARNING: {d} not found")
        continue
    level_name = os.path.basename(d)
    files = sorted(glob.glob(os.path.join(d, '*.json')))
    count = 0
    for fp in files:
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                task = json.load(f)
            # Нормализуем поля под формат final_db_1_5
            normalized = {
                'id': task.get('id'),
                'task_text': task.get('task_text', ''),
                'solution': task.get('solution', ''),
                'correct_answer': task.get('correct_answer', ''),
                'topic': task.get('topic', ''),
                'difficulty_level': task.get('difficulty_level', task.get('real_level', 6)),
                'class_level': task.get('class_level', 9),
                'source': task.get('source', 'gen_678'),
                'key_method': task.get('key_method', ''),
            }
            tasks_678.append(normalized)
            count += 1
        except Exception as e:
            print(f"  ERROR loading {fp}: {e}")
    print(f"  {level_name}: {count} tasks")

print(f"  Total 6-8 tasks: {len(tasks_678)}")

# 3. Объединяем
all_tasks = db15 + tasks_678
print(f"\nTotal combined: {len(all_tasks)} tasks")

# 4. Считаем по уровням
levels = {}
for t in all_tasks:
    lv = t.get('difficulty_level', '?')
    levels[str(lv)] = levels.get(str(lv), 0) + 1
print("\nBy level:")
for k in sorted(levels.keys(), key=lambda x: (len(x), x)):
    print(f"  Level {k}: {levels[k]}")

# 5. Сохраняем
OUT = os.path.join(BASE, 'adaptive_all_1_8.json')
print(f"\nSaving to {OUT}...")
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(all_tasks, f, ensure_ascii=False, indent=2)
size_mb = os.path.getsize(OUT) / 1024 / 1024
print(f"Done! {size_mb:.1f} MB")
