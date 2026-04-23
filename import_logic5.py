#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Импорт задач по Логике из grade6_logic5.jsonl"""

import json
import re
from app import app
from models import db, AdaptiveTask


def clean(text):
    return re.sub(r'\s+', ' ', text or '').strip()


with app.app_context():
    tasks = []
    with open('grade6_logic5.jsonl', 'r', encoding='utf-8') as f:
        for line in f:
            try:
                tasks.append(json.loads(line))
            except Exception:
                pass

    imported = 0
    skipped = 0
    for t in tasks:
        q = clean(t.get('question', ''))
        if not q or len(q) < 20:
            skipped += 1
            continue
        existing = AdaptiveTask.query.filter_by(class_level=6, task_text=q).first()
        if existing:
            skipped += 1
            continue
        task = AdaptiveTask(
            class_level=6,
            difficulty_level=t.get('level', 3),
            topic=t.get('topic', 'Логика (рыцари и лжецы, логические таблицы)'),
            task_text=q,
            solution=clean(t.get('explanation', '')),
            correct_answer=clean(t.get('answer', '')),
            criteria_1_point='Частичное решение',
            criteria_2_points='Полное правильное решение'
        )
        db.session.add(task)
        imported += 1

    db.session.commit()

    total = AdaptiveTask.query.filter_by(class_level=6).count()
    logic = AdaptiveTask.query.filter_by(
        class_level=6,
        topic='Логика (рыцари и лжецы, логические таблицы)'
    ).count()

    print(f"[OK] Импортировано: {imported}")
    print(f"[SKIP] Пропущено: {skipped}")
    print(f"[TOTAL] Всего задач 6 класса: {total}")
    print(f"[LOGIC] Логика: {logic}")
