#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Импорт олимпиадных задач для 7 класса в БД.
Вход: grade7_olympiad_RAW.jsonl (или grade7_olympiad_CLEAN.jsonl)
"""

import json
import re
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from models import db, AdaptiveTask


def clean_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def is_valid(task: dict) -> bool:
    if not all(k in task for k in ['statement', 'answer', 'solution']):
        return False
    if not task['statement'] or not task['answer']:
        return False
    if len(task['statement']) < 20:
        return False
    return True


def import_grade7(input_file='grade7_olympiad_RAW.jsonl'):
    print("\n" + "="*70)
    print("ИМПОРТ ЗАДАЧ ДЛЯ 7 КЛАССА В БД")
    print("="*70)
    print(f"[INPUT] {input_file}")
    print("="*70 + "\n")

    with app.app_context():
        tasks = []
        seen = set()

        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    tasks.append(json.loads(line))
                except Exception:
                    pass

        print(f"[INFO] Прочитано задач: {len(tasks)}")

        existing = AdaptiveTask.query.filter_by(class_level=7).count()
        if existing > 0:
            print(f"[INFO] В БД уже есть {existing} задач для 7 класса")
            resp = input("Удалить и импортировать заново? (yes/no): ")
            if resp.lower() == 'yes':
                AdaptiveTask.query.filter_by(class_level=7).delete()
                db.session.commit()
                print(f"[OK] Удалено {existing} старых задач")
            else:
                print("[STOP] Импорт отменен")
                return

        imported = 0
        skipped_invalid = 0
        skipped_dup = 0

        for t in tasks:
            if not is_valid(t):
                skipped_invalid += 1
                continue

            statement = clean_text(t['statement'])
            q_key = statement.lower()[:100]
            if q_key in seen:
                skipped_dup += 1
                continue
            seen.add(q_key)

            # Маппинг topic_id → полное название темы
            topic_names = {
                'algebra_expressions': 'Алгебраические тождества и преобразования',
                'linear_equations': 'Линейные уравнения и системы',
                'functions': 'Функции и графики',
                'geometry_basics': 'Начала геометрии',
                'triangles': 'Треугольники',
                'proofs_geometry': 'Геометрические доказательства',
                'combinatorics_7': 'Комбинаторика',
                'number_theory_7': 'Теория чисел',
                'logic_invariants': 'Логика и инварианты',
                'inequalities_7': 'Неравенства',
            }
            topic_id = t.get('topic', '')
            topic_name = topic_names.get(topic_id, t.get('topic_name', topic_id))

            task = AdaptiveTask(
                class_level=7,
                difficulty_level=t.get('level', 3),
                topic=topic_name,
                task_text=statement,
                solution=clean_text(t.get('solution', '')),
                correct_answer=clean_text(t.get('answer', '')),
                criteria_1_point='Частичное решение или правильная идея',
                criteria_2_points='Полное правильное решение'
            )
            db.session.add(task)
            imported += 1

            if imported % 50 == 0:
                db.session.commit()
                print(f"[PROGRESS] Импортировано: {imported}")

        db.session.commit()

        total = AdaptiveTask.query.filter_by(class_level=7).count()

        print(f"\n{'='*70}")
        print("РЕЗУЛЬТАТЫ ИМПОРТА")
        print("="*70)
        print(f"[OK] Импортировано: {imported}")
        print(f"[SKIP] Невалидных: {skipped_invalid}")
        print(f"[SKIP] Дублей: {skipped_dup}")
        print(f"[TOTAL] Всего задач для 7 класса в БД: {total}")
        print("="*70 + "\n")

        # Статистика по темам
        from sqlalchemy import func
        topics = db.session.query(
            AdaptiveTask.topic,
            func.count(AdaptiveTask.id)
        ).filter_by(class_level=7).group_by(AdaptiveTask.topic).all()

        print("Распределение по темам:")
        for topic, count in sorted(topics, key=lambda x: x[1]):
            status = "✅" if count >= 80 else "⚠️"
            print(f"  {status} {topic}: {count}")


if __name__ == "__main__":
    import_grade7()
