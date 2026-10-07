# -*- coding: utf-8 -*-
"""Импорт FORMYLA_L1_L5_TOP5.jsonl в adaptive_tasks."""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from app import app
from models import db, AdaptiveTask

app.app_context().push()

# Проверим, сколько уже есть
existing = AdaptiveTask.query.count()
print(f"До импорта: {existing} задач в adaptive_tasks")

if existing > 0:
    print("Задачи уже есть, пропускаем импорт.")
    sys.exit(0)

jsonl_path = os.path.join(os.path.dirname(__file__), 'FORMYLA_L1_L5_TOP5.jsonl')
print(f"Читаем {jsonl_path}...")

count = 0
batch = []
with open(jsonl_path, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Маппинг полей JSONL -> AdaptiveTask
        methods_val = d.get('methods', [])
        if isinstance(methods_val, list):
            methods_json = json.dumps(methods_val, ensure_ascii=False)
        elif isinstance(methods_val, str):
            methods_json = methods_val
        else:
            methods_json = None

        task = AdaptiveTask(
            task_text=d.get('statement', ''),
            correct_answer=d.get('answer', ''),
            solution=d.get('solution', ''),
            subject=(d.get('section', '') or ''),
            topic=(d.get('theme', '') or ''),
            class_level=int(d.get('grade', 9)),
            difficulty_level=int(d.get('level', 1)),
            source='formyla_L1_L5_TOP5',
            origin=d.get('origin', ''),
            task_type='problem',
            methods_json=methods_json,
            theme_id=d.get('theme_id', ''),
            criteria_1_point='',
            criteria_2_points='',
        )
        batch.append(task)
        count += 1
        if len(batch) >= 1000:
            db.session.bulk_save_objects(batch)
            db.session.commit()
            print(f"  Импортировано {count} задач...")
            batch = []

if batch:
    db.session.bulk_save_objects(batch)
    db.session.commit()

print(f"ГОТОВО: импортировано {count} задач в adaptive_tasks")

# Проверим распределение
from sqlalchemy import func
grades = db.session.query(AdaptiveTask.class_level, func.count()).group_by(AdaptiveTask.class_level).all()
print("По классам:")
for g, c in sorted(grades, key=lambda x: x[0] or 0):
    print(f"  Класс {g}: {c} задач")

levels = db.session.query(AdaptiveTask.difficulty_level, func.count()).group_by(AdaptiveTask.difficulty_level).all()
print("По уровням:")
for l, c in sorted(levels, key=lambda x: x[0] or 0):
    print(f"  Уровень {l}: {c} задач")
