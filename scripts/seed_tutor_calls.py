"""
scripts/seed_tutor_calls.py

Заполняет tutor_calls тестовыми данными для проверки дашборда.
Симулирует реальные вызовы тьютора на разных задачах.

Запуск: python scripts/seed_tutor_calls.py
"""
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app import app, db
from models import AdaptiveTask
from services.ai_tutor_v2 import tutor_explain
from ai.deepseek_client import DeepSeekClient

# Задачи для теста: берём разные темы и классы
TEST_CASES = [
    # (task_id, user_answer_wrong)
    # Задача 1650 — уже помечена, пропускаем
    # Берём несколько активных задач
]

with app.app_context():
    print("=== Seed tutor_calls ===")
    print("Ищем активные задачи для теста...")

    # Берём 5 задач из разных тем
    tasks = AdaptiveTask.query.filter(
        AdaptiveTask.is_flagged == False,
        AdaptiveTask.correct_answer.isnot(None),
        AdaptiveTask.correct_answer != '',
    ).order_by(AdaptiveTask.id).limit(5).all()

    if not tasks:
        print("❌ Нет активных задач!")
        sys.exit(1)

    print(f"Найдено {len(tasks)} задач для теста")
    print()

    ai_client = DeepSeekClient()
    results_summary = []

    for i, task in enumerate(tasks, 1):
        print(f"[{i}/{len(tasks)}] Задача id={task.id} | {task.topic[:40]} | класс {task.class_level}")
        print(f"  Условие: {task.task_text[:80]}...")
        print(f"  Правильный ответ: {task.correct_answer}")

        # Симулируем неверный ответ ученика
        wrong_answer = "42"  # заведомо неверный

        try:
            result = tutor_explain(task, wrong_answer, ai_client)

            # Логируем в tutor_calls
            from app import _log_tutor_call
            _log_tutor_call(task.id, wrong_answer, result)

            print(f"  ✅ status={result['status']}, errors={result['errors']}")
            print(f"  Ответ ученику: {result['solution'][:100]}...")
            results_summary.append({
                'task_id': task.id,
                'status': result['status'],
                'errors': result['errors'],
            })
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
            results_summary.append({
                'task_id': task.id,
                'status': 'error',
                'errors': [str(e)],
            })

        print()

    # Итог
    print("=" * 50)
    print("ИТОГ:")
    ok_count = sum(1 for r in results_summary if r['status'] == 'ok')
    fallback_count = sum(1 for r in results_summary if r['status'] == 'fallback')
    error_count = sum(1 for r in results_summary if r['status'] == 'error')
    total = len(results_summary)

    print(f"  Всего вызовов: {total}")
    print(f"  OK: {ok_count} ({ok_count*100//total if total else 0}%)")
    print(f"  Fallback: {fallback_count} ({fallback_count*100//total if total else 0}%)")
    print(f"  Ошибки: {error_count}")
    print()

    # Статистика из БД
    from sqlalchemy import text
    stats = db.session.execute(text("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) as ok,
            SUM(CASE WHEN status='fallback' THEN 1 ELSE 0 END) as fallback
        FROM tutor_calls
    """)).fetchone()

    print(f"Всего в tutor_calls: {stats.total}")
    print(f"  OK: {stats.ok}")
    print(f"  Fallback: {stats.fallback}")

    # Топ-5 задач с fallback
    top = db.session.execute(text("""
        SELECT tc.task_id, COUNT(*) as fails,
               at.topic, at.class_level, at.correct_answer,
               GROUP_CONCAT(DISTINCT tc.validation_errors) as errors
        FROM tutor_calls tc
        LEFT JOIN adaptive_tasks at ON at.id = tc.task_id
        WHERE tc.status = 'fallback'
        GROUP BY tc.task_id
        ORDER BY fails DESC
        LIMIT 5
    """)).fetchall()

    if top:
        print()
        print("Топ-5 задач с fallback:")
        for r in top:
            print(f"  id={r[0]} fails={r[1]} class={r[3]} answer={repr(r[4])} "
                  f"topic={r[2][:35] if r[2] else '?'} errors={r[5]}")
    else:
        print("Нет задач с fallback в tutor_calls")
