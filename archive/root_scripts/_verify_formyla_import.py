#!/usr/bin/env python3
"""Проверить, что задачи formyla_final корректно импортированы в task_bank."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app import app
from models import db
from curator.task_bank import TaskBank
from curator.config import DIAG_TOPICS

with app.app_context():
    total = TaskBank.query.count()
    formyla = TaskBank.query.filter(TaskBank.source == 'formyla_final').count()
    seed = TaskBank.query.filter(TaskBank.source == 'seed').count()
    
    print(f"Всего в task_bank: {total}")
    print(f"  source=formyla_final: {formyla}")
    print(f"  source=seed: {seed}")
    print()
    
    for t in DIAG_TOPICS:
        count = TaskBank.query.filter(TaskBank.topic == t).count()
        diffs = sorted(set(d[0] for d in db.session.query(TaskBank.difficulty)
                           .filter(TaskBank.topic == t).distinct().all()))
        grade_tags = set()
        for task in TaskBank.query.filter(TaskBank.topic == t).limit(3):
            if task.tags:
                import json
                try:
                    for tag in json.loads(task.tags):
                        if tag.startswith('class_'):
                            grade_tags.add(tag)
                except: pass
        print(f"  {t}: {count} задач, difficulty={diffs}, tags_sample={grade_tags}")
    
    # Sample a few tasks
    print("\nПримеры задач:")
    for task in TaskBank.query.order_by(TaskBank.id).limit(5):
        print(f"  #{task.id} topic={task.topic} diff={task.difficulty}")
        print(f"    statement: {task.statement[:80]}...")
        print(f"    answer: {task.answer}")
        print()
