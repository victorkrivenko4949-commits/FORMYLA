# -*- coding: utf-8 -*-
"""P7 Task 2: прогон 100 учеников × 30 дней без LIMIT 500."""
import sys, os, json, random, time
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from models import db, AdaptiveTask, TaskAssignmentHistory, User
from models_curator import CuratorState
from daily_tasks.models import DailyTaskSet, DailyTaskItem
from services.daily_task_rotation import pick_daily_set, get_daily_task_count

app.app_context().push()

# Сколько задач в базе
total = AdaptiveTask.query.filter(
    AdaptiveTask.correct_answer.isnot(None),
    AdaptiveTask.correct_answer != '',
    AdaptiveTask.task_text.isnot(None),
    AdaptiveTask.task_text != '',
).count()
print(f"Всего валидных задач в AdaptiveTask: {total}")

# Очистим историю и DailyTaskSet от предыдущих прогонов
print("Очистка старых данных...")
TaskAssignmentHistory.query.delete()
DailyTaskItem.query.delete()
DailyTaskSet.query.delete()
CuratorState.query.delete()
db.session.commit()

# Создаём 100 учеников без User (user_id 1..100), им нужны CuratorState
# Инициализируем анкету для каждого
for uid in range(1, 101):
    cs = CuratorState.query.filter_by(user_id=uid).first()
    if not cs:
        cs = CuratorState(user_id=uid)
        db.session.add(cs)
    # Устанавливаем onboarding с daily_tasks=5, route_ceiling=5, grade=9
    cs.prep_state = {
        'onboarding': {
            'daily_tasks': 5,
            'route_ceiling': 5,
            'grade': 9,
            'target_level': 3,
        }
    }
    cs.level_mu = 2.0
    cs.level_sigma = 1.5
    cs.level_by_section = '{}'
db.session.commit()
print("Создано 100 учеников с grade=9, mu=2.0")

# Прогон: 30 дней, каждый день pick_daily_set для каждого ученика
all_assigned_task_ids = set()
student_task_sets = {uid: set() for uid in range(1, 101)}

for day in range(1, 31):
    # Подменяем дату: DailyTaskSet привязан к target_date, надо его удалять
    # чтобы pick_daily_set генерировал новый
    DailyTaskItem.query.delete()
    DailyTaskSet.query.delete()
    db.session.commit()
    
    for uid in range(1, 101):
        try:
            result = pick_daily_set(uid, force_regenerate=True)
            for t in result.get('tasks', []):
                tid = t['task_id']
                all_assigned_task_ids.add(tid)
                student_task_sets[uid].add(tid)
        except Exception as e:
            print(f"  ERROR user={uid} day={day}: {e}")

print(f"\n=== РЕЗУЛЬТАТЫ ПРОГОНА (100 учеников × 30 дней) ===")
print(f"Всего РАЗНЫХ задач с хотя бы одной выдачей: {len(all_assigned_task_ids)}")

# Статистика по ученикам
total_tasks = sum(len(v) for v in student_task_sets.values())
print(f"Всего выдач: {total_tasks}")
print(f"В среднем на ученика уникальных задач: {total_tasks/100:.1f}")

# Распределение уникальных задач по ученикам
counts = [len(v) for v in student_task_sets.values()]
print(f"Мин уникальных у одного ученика: {min(counts)}")
print(f"Макс уникальных у одного ученика: {max(counts)}")
print(f"Медиана уникальных: {sorted(counts)[50]}")

# Посмотрим, сколько задач каждого difficulty_level было выдано
from collections import Counter
level_counts = Counter()
for tid in all_assigned_task_ids:
    task = AdaptiveTask.query.get(tid)
    if task:
        level_counts[task.difficulty_level] += 1
print(f"\nРаспределение по уровням выданных задач: {dict(sorted(level_counts.items()))}")

print("\nГОТОВО.")
