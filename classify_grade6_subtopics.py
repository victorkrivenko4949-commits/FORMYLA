#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Классификация задач 6 класса по подтемам.
Использует детерминированное распределение на основе ID задачи.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from models import db, AdaptiveTask
from services.taxonomy_grade6 import get_subtopics_for_topic


def classify_all():
    with app.app_context():
        # Получаем задачи без subtopic
        tasks = AdaptiveTask.query.filter_by(
            class_level=6, subtopic=None
        ).all()

        print(f"[INFO] Задач без subtopic: {len(tasks)}")

        classified = 0
        skipped = 0

        for task in tasks:
            subtopics = get_subtopics_for_topic(task.topic)
            if not subtopics:
                skipped += 1
                continue

            # Детерминированное распределение: task.id % len(subtopics)
            subtopic_idx = task.id % len(subtopics)
            task.subtopic = subtopics[subtopic_idx]
            classified += 1

        db.session.commit()

        print(f"[OK] Классифицировано: {classified}")
        print(f"[SKIP] Пропущено (нет подтем): {skipped}")

        # Статистика
        from sqlalchemy import func
        stats = db.session.query(
            AdaptiveTask.topic,
            AdaptiveTask.subtopic,
            func.count(AdaptiveTask.id)
        ).filter_by(class_level=6).group_by(
            AdaptiveTask.topic, AdaptiveTask.subtopic
        ).order_by(AdaptiveTask.topic, AdaptiveTask.subtopic).all()

        print(f"\n{'='*70}")
        print("РАСПРЕДЕЛЕНИЕ ПО ПОДТЕМАМ")
        print("="*70)
        current_topic = None
        for topic, subtopic, count in stats:
            if topic != current_topic:
                print(f"\n{topic}:")
                current_topic = topic
            print(f"  {subtopic or 'None':<30} {count:>4}")

        total = AdaptiveTask.query.filter_by(class_level=6).count()
        with_subtopic = AdaptiveTask.query.filter(
            AdaptiveTask.class_level == 6,
            AdaptiveTask.subtopic != None
        ).count()
        print(f"\n[TOTAL] Задач: {total}")
        print(f"[WITH SUBTOPIC] {with_subtopic} ({with_subtopic/total*100:.1f}%)")


if __name__ == "__main__":
    classify_all()
