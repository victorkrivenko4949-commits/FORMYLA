"""
Скрипт автоматической пометки задач с >= 3 fallback за 7 дней.
Запуск: python scripts/auto_mark_problem_tasks.py

Можно добавить в cron или запускать вручную.
"""
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from datetime import datetime
from app import app, db
from models import AdaptiveTask
from sqlalchemy import text

with app.app_context():
    print("=== Авто-пометка задач с fallback ===")

    # Задачи с >= 3 fallback за 7 дней
    problems = db.session.execute(text("""
        SELECT task_id, COUNT(*) as fails
        FROM tutor_calls
        WHERE status='fallback'
          AND created_at > datetime('now', '-7 days')
        GROUP BY task_id
        HAVING fails >= 3
    """)).fetchall()

    print(f"Найдено задач с >= 3 fallback: {len(problems)}")

    marked = 0
    for row in problems:
        task = AdaptiveTask.query.get(row.task_id)
        if task and not task.is_flagged:
            task.is_flagged = True
            task.flagged_reason = (
                f'auto: {row.fails} fallback за 7 дней (tutor_v2)'
            )
            print(f"  ✅ Помечена задача #{row.task_id} "
                  f"(тема: {task.topic}, класс: {task.class_level}, "
                  f"ответ: {task.correct_answer}) — {row.fails} fallback")
            marked += 1
        elif task and task.is_flagged:
            print(f"  ⏭  Задача #{row.task_id} уже помечена")
        else:
            print(f"  ❌ Задача #{row.task_id} не найдена в БД")

    db.session.commit()
    print(f"\nИтого помечено: {marked} задач")

    # Статистика по всем помеченным
    flagged_count = AdaptiveTask.query.filter_by(is_flagged=True).count()
    total_count = AdaptiveTask.query.count()
    print(f"Всего помечено: {flagged_count} из {total_count} задач "
          f"({flagged_count/total_count*100:.1f}%)")

    # Статистика tutor_calls
    stats = db.session.execute(text("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) as ok,
            SUM(CASE WHEN status='fallback' THEN 1 ELSE 0 END) as fallback
        FROM tutor_calls
        WHERE created_at > datetime('now', '-7 days')
    """)).fetchone()

    if stats.total:
        print(f"\nСтатистика тьютора за 7 дней:")
        print(f"  Всего вызовов: {stats.total}")
        print(f"  OK: {stats.ok} ({stats.ok/stats.total*100:.1f}%)")
        print(f"  Fallback: {stats.fallback} ({stats.fallback/stats.total*100:.1f}%)")
    else:
        print("\nТьютор ещё не вызывался за последние 7 дней")
