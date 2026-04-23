#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Импорт балансировочных задач для 6 класса из grade6_balance_RAW.jsonl
"""

import json
import re
from app import app
from models import db, AdaptiveTask


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def is_valid(task: dict) -> bool:
    if not all(k in task for k in ['question', 'answer', 'explanation']):
        return False
    if not task['question'] or not task['answer']:
        return False
    if len(task['question']) < 20:
        return False
    return True


def import_balance_tasks(input_file='grade6_balance_RAW.jsonl'):
    print("\n" + "="*70)
    print("ИМПОРТ БАЛАНСИРОВОЧНЫХ ЗАДАЧ ДЛЯ 6 КЛАССА")
    print("="*70)
    print(f"[INPUT] {input_file}")
    print("="*70 + "\n")

    with app.app_context():
        tasks = []
        seen_questions = set()

        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    task = json.loads(line)
                    tasks.append(task)
                except Exception:
                    pass

        print(f"[INFO] Прочитано задач: {len(tasks)}")

        imported = 0
        skipped_invalid = 0
        skipped_dup = 0

        for task_data in tasks:
            if not is_valid(task_data):
                skipped_invalid += 1
                continue

            question = clean_text(task_data['question'])
            q_key = question.lower()[:100]
            if q_key in seen_questions:
                skipped_dup += 1
                continue

            # Проверка дубликата в БД
            existing = AdaptiveTask.query.filter_by(
                class_level=6,
                task_text=question
            ).first()
            if existing:
                skipped_dup += 1
                continue

            seen_questions.add(q_key)

            task = AdaptiveTask(
                class_level=6,
                difficulty_level=task_data.get('level', 3),
                topic=task_data.get('topic', ''),
                task_text=question,
                solution=clean_text(task_data.get('explanation', '')),
                correct_answer=clean_text(task_data.get('answer', '')),
                criteria_1_point="Частичное решение или правильная идея",
                criteria_2_points="Полное правильное решение"
            )
            db.session.add(task)
            imported += 1

            if imported % 50 == 0:
                db.session.commit()
                print(f"[PROGRESS] Импортировано: {imported}")

        db.session.commit()

        total = AdaptiveTask.query.filter_by(class_level=6).count()

        print(f"\n{'='*70}")
        print("РЕЗУЛЬТАТЫ ИМПОРТА")
        print("="*70)
        print(f"[OK] Импортировано: {imported}")
        print(f"[SKIP] Невалидных: {skipped_invalid}")
        print(f"[SKIP] Дублей: {skipped_dup}")
        print(f"[TOTAL] Всего задач для 6 класса в БД: {total}")
        print("="*70 + "\n")

        # Статистика по темам
        from sqlalchemy import func
        topics = db.session.query(
            AdaptiveTask.topic,
            func.count(AdaptiveTask.id)
        ).filter_by(class_level=6).group_by(AdaptiveTask.topic).all()

        print("Распределение по темам:")
        for topic, count in sorted(topics, key=lambda x: x[1]):
            status = "✅" if count >= 80 else "⚠️"
            print(f"  {status} {topic}: {count}")


if __name__ == "__main__":
    import_balance_tasks()
