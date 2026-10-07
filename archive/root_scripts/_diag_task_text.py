# -*- coding: utf-8 -*-
"""Query the database to see actual task_text content."""
from app import app
from models import AdaptiveTask
import re

with app.app_context():
    # Find tasks with "При каких" in the text
    tasks = AdaptiveTask.query.filter(
        AdaptiveTask.task_text.like('%При каких%')
    ).limit(5).all()
    
    print(f"Found {len(tasks)} tasks with 'При каких'")
    for t in tasks:
        print(f"\n--- Task ID={t.id} ---")
        print(f"task_text repr: {repr(t.task_text[:300])}")
        print(f"task_text raw: |{t.task_text[:300]}|")
        print(f"correct_answer: {t.correct_answer}")
        print(f"solution: {repr(t.solution[:200] if t.solution else '')}")
        print(f"class_level: {t.class_level}")
        print(f"difficulty_level: {t.difficulty_level}")
        print()

    # Also check a few random tasks to see format
    print("=== Random tasks samples ===")
    random_tasks = AdaptiveTask.query.filter(
        AdaptiveTask.class_level == 9
    ).limit(3).all()
    for t in random_tasks:
        print(f"\n--- Task ID={t.id} (grade {t.class_level}) ---")
        text_preview = t.task_text[:200] if t.task_text else "EMPTY"
        print(f"task_text: {repr(text_preview)}")
        print(f"Has $: {'$' in (t.task_text or '')}")
