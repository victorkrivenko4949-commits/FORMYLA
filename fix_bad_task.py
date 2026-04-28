# -*- coding: utf-8 -*-
"""Find and fix the broken НОД(n,50)·НОК(n,50)/n=10 task in DB.
Mathematical fact: НОД(n,50)·НОК(n,50) = 50n, so the expression = 50 for all n.
The task says = 10 which is impossible. Fix: delete the task.
"""
import sys
sys.path.insert(0, '.')

from app import app
from models import db, AdaptiveTask

with app.app_context():
    # Search by task text
    tasks = AdaptiveTask.query.filter(
        AdaptiveTask.task_text.like('%НОД%50%НОК%50%')
    ).all()

    print(f"Found {len(tasks)} tasks matching НОД/НОК(n,50) pattern:")
    for t in tasks:
        print(f"\nID={t.id} class_level={t.class_level} difficulty={t.difficulty_level}")
        print(f"  topic: {t.topic}")
        print(f"  text: {t.task_text[:300]}")
        print(f"  answer: {t.correct_answer}")
        print(f"  flagged: {t.is_flagged}, reports: {t.reports_count}")

    if tasks:
        print(f"\nDeleting {len(tasks)} broken task(s)...")
        for t in tasks:
            print(f"  Deleting ID={t.id}: {t.task_text[:80]}...")
            db.session.delete(t)
        db.session.commit()
        print("DONE: Tasks deleted from DB.")
    else:
        print("No tasks found with that pattern.")
