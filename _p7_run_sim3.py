# -*- coding: utf-8 -*-
"""P7 Task 3: 100 учеников с разными mu, вероятностные ответы."""
import sys, os, json, random, math
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from models import db, AdaptiveTask, TaskAssignmentHistory
from models_curator import CuratorState
from daily_tasks.models import DailyTaskSet, DailyTaskItem
from services.daily_task_rotation import pick_daily_set, record_daily_answer
from services.level_engine import get_state

app.app_context().push()

# Очистка
print("Очистка старых данных...")
TaskAssignmentHistory.query.delete()
DailyTaskItem.query.delete()
DailyTaskSet.query.delete()
CuratorState.query.delete()
db.session.commit()

# 100 учеников: примерно поровну mu 2.0, 2.5, 3.0, 3.5, 4.0
mu_values = [2.0] * 20 + [2.5] * 20 + [3.0] * 20 + [3.5] * 20 + [4.0] * 20
random.shuffle(mu_values)  # перемешиваем

student_mu = {}  # user_id -> начальный mu
for uid in range(1, 101):
    mu = mu_values[uid - 1]
    student_mu[uid] = mu
    cs = CuratorState.query.filter_by(user_id=uid).first()
    if not cs:
        cs = CuratorState(user_id=uid)
        db.session.add(cs)
    cs.prep_state = {
        'onboarding': {
            'daily_tasks': 5,
            'route_ceiling': 5,
            'grade': 9,
            'target_level': 3,
        }
    }
    cs.level_mu = mu
    cs.level_sigma = 1.5
    cs.level_by_section = '{}'
db.session.commit()

print(f"Создано 100 учеников: mu распределение = {Counter(mu_values)}")

# Функция вероятности успеха
def success_probability(student_mu_value, task_difficulty):
    """Вероятность правильного ответа: сигмоида от разницы mu - level."""
    delta = student_mu_value - task_difficulty
    # Крутизна = 2.0, чтобы mu=2 на L2 -> ~50%, mu=3 на L2 -> ~88%
    return 1.0 / (1.0 + math.exp(-delta * 2.0))

# Прогон 30 дней
all_assigned_task_ids = set()
level_distribution = Counter()
empty_sets_count = 0
day_mu_history = defaultdict(list)  # uid -> [mu по дням]

for day in range(1, 31):
    # Удаляем старые DailyTaskSet перед каждым днём
    DailyTaskItem.query.delete()
    DailyTaskSet.query.delete()
    db.session.commit()
    
    for uid in range(1, 101):
        try:
            result = pick_daily_set(uid, force_regenerate=True)
            tasks = result.get('tasks', [])
            if not tasks:
                empty_sets_count += 1
                continue
            
            # Записываем mu ученика ДО ответов
            state_before = get_state(uid)
            day_mu_history[uid].append(state_before['mu'])
            
            # Для каждой задачи моделируем ответ
            for t in tasks:
                tid = t['task_id']
                diff = t.get('difficulty_level', 2)
                all_assigned_task_ids.add(tid)
                level_distribution[diff] += 1
                
                # Берём текущий mu
                current_state = get_state(uid)
                p_success = success_probability(current_state['mu'], diff)
                is_correct = random.random() < p_success
                
                # Ищем DailyTaskItem.id для этой задачи (только что созданный)
                # Но это неудобно — проще сразу вызывать record_result
                # через level_engine, т.к. record_daily_answer требует item_id
                # Упрощённо: обновляем mu/sigma напрямую
                from services.level_engine import record_result
                # Определяем раздел
                task = AdaptiveTask.query.get(tid)
                section = None
                if task:
                    from services.daily_task_rotation import _classify_section
                    section = _classify_section(task)
                
                record_result(uid, section, diff, is_correct)
                
        except Exception as e:
            print(f"  ERROR user={uid} day={day}: {e}")

# Финальные результаты
print(f"\n=== РЕЗУЛЬТАТЫ ПРОГОНА (100 уч. × 30 дней, разные mu) ===")
print(f"Всего разных задач с выдачей: {len(all_assigned_task_ids)}")
print(f"Пустых DailyTaskSet: {empty_sets_count}")

print(f"\nРаспределение выдач по уровням:")
for lvl in sorted(level_distribution.keys()):
    print(f"  Уровень {lvl}: {level_distribution[lvl]}")

print(f"\nРазброс mu на 30-й день:")
final_mus = []
mu_groups = defaultdict(list)
for uid in range(1, 101):
    state = get_state(uid)
    final_mu = state['mu']
    final_mus.append(final_mu)
    start_mu = student_mu[uid]
    # Определяем группу по стартовому mu
    mu_bucket = str(start_mu)
    mu_groups[mu_bucket].append(final_mu)

print(f"  Мин: {min(final_mus):.3f}, Макс: {max(final_mus):.3f}, Среднее: {sum(final_mus)/len(final_mus):.3f}")

for start_mu in sorted(mu_groups.keys(), key=float):
    values = mu_groups[start_mu]
    avg = sum(values) / len(values)
    print(f"  Старт mu={start_mu}: финал mu={min(values):.2f}..{max(values):.2f}, среднее={avg:.3f}")

print(f"\nДинамика mu (выборка 5 учеников из разных групп):")
sample_uids = [1, 21, 41, 61, 81]  # первые из каждой группы по 20
for uid in sample_uids:
    history = day_mu_history[uid]
    print(f"  Ученик {uid} (старт={student_mu[uid]}): {', '.join(f'{m:.2f}' for m in history[:10])}... -> {history[-1]:.2f}")

print("\nГОТОВО.")
