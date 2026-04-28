# -*- coding: utf-8 -*-
"""Find the broken НОД(n,50)·НОК(n,50)/n=10 task in DB"""
import sys
sys.path.insert(0, '.')

from app import app
from models import db, AdaptiveTask

with app.app_context():
    # Search by task text
    tasks = AdaptiveTask.query.filter(
        AdaptiveTask.task_text.like('%НОД%50%НОК%50%')
    ).all()
    
    if not tasks:
        tasks = AdaptiveTask.query.filter(
            AdaptiveTask.task_text.like('%НОД(n%')
        ).all()
    
    if not tasks:
        tasks = AdaptiveTask.query.filter(
            AdaptiveTask.task_text.like('%НОК(n%')
        ).all()

    print(f"Found {len(tasks)} tasks matching НОД/НОК pattern:")
    for t in tasks:
        print(f"\nID={t.id} grade={t.grade} level={t.difficulty_level}")
        print(f"  text: {t.task_text[:200]}")
        print(f"  answer: {t.correct_answer}")
