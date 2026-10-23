# -*- coding: utf-8 -*-
"""P7 Task 4: диагностика цепочки задач дня."""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from app import app
from models import db, User
from models_curator import CuratorState
from daily_tasks.models import DailyTaskSet, DailyTaskItem

ctx = app.app_context()
ctx.push()

# ШАГ 1: пользователь
print("=== ШАГ 1: Создаём пользователя ===")
user = User.query.filter_by(email='p7task4@formyla.ru').first()
if not user:
    user = User(
        email='p7task4@formyla.ru',
        nickname='p7task4',
        name='P7 Test User',
        preferred_grade=9,
    )
    db.session.add(user)
    db.session.commit()
    print(f"  Создан user_id={user.id}")
else:
    print(f"  Существующий user_id={user.id} nickname={user.nickname}")

# Очищаем старые сеты
DailyTaskItem.query.filter(DailyTaskItem.daily_set_id.in_(
    db.session.query(DailyTaskSet.id).filter_by(user_id=user.id)
)).delete(synchronize_session=False)
DailyTaskSet.query.filter_by(user_id=user.id).delete()
db.session.commit()

# Создаём CuratorState
cs = CuratorState.query.filter_by(user_id=user.id).first()
if cs:
    db.session.delete(cs)
    db.session.commit()
cs = CuratorState(user_id=user.id)
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
cs.onboarding_done = True
db.session.add(cs)
db.session.commit()
print(f"  CuratorState создан: mu={cs.level_mu}")

# ШАГ 2: pick_daily_set
print("\n=== ШАГ 2: Вызов pick_daily_set ===")
from services.daily_task_rotation import pick_daily_set
result = pick_daily_set(user.id, force_regenerate=False)
print(f"  count={result.get('count', 0)} tasks")
for t in result.get('tasks', []):
    print(f"    task_id={t['task_id']} level={t.get('difficulty_level')} subject={t.get('subject')}")

# ШАГ 3: проверка БД
print("\n=== ШАГ 3: DailyTaskSet в БД ===")
dts = DailyTaskSet.query.filter_by(user_id=user.id).first()
if dts:
    print(f"  SET: id={dts.id} status={dts.status} class_level={dts.class_level}")
    items = DailyTaskItem.query.filter_by(daily_set_id=dts.id).order_by(DailyTaskItem.position).all()
    print(f"  ITEMS: {len(items)} шт.")
    for it in items:
        print(f"    id={it.id} pos={it.position} slot={it.slot_kind} subject={it.subject} level={it.difficulty_level}")
        print(f"         task_text[:60]={it.task_text[:60] if it.task_text else 'EMPTY!'}")
else:
    print("  DailyTaskSet: NOT FOUND!")

# ШАГ 4: Симуляция маршрута (без HTTP)
print("\n=== ШАГ 4: Вызов services.get_daily_tasks ===")
from daily_tasks.services import get_daily_tasks, today_in_user_tz
svc = get_daily_tasks(user.id)
print(f"  status={svc['status']}")
print(f"  daily_set_id={svc.get('daily_set_id')}")
print(f"  items count={len(svc.get('items', []))}")
for it in svc.get('items', []):
    print(f"    id={it['id']} pos={it['position']} topic={it.get('topic')} text[:50]={it.get('task_text','')[:50]}")

# ШАГ 5: Повторный заход
print("\n=== ШАГ 5: Повторный заход (идемпотентность) ===")
prev_sets = DailyTaskSet.query.filter_by(user_id=user.id).count()
prev_items_count = DailyTaskItem.query.filter_by(daily_set_id=dts.id).count() if dts else 0

result2 = pick_daily_set(user.id, force_regenerate=False)
after_sets = DailyTaskSet.query.filter_by(user_id=user.id).count()
after_items_count = DailyTaskItem.query.filter_by(daily_set_id=dts.id).count() if dts else 0

print(f"  DailyTaskSet: было {prev_sets} -> стало {after_sets}")
print(f"  DailyTaskItem: было {prev_items_count} -> стало {after_items_count}")
new_rows = (after_sets - prev_sets) + (after_items_count - prev_items_count)
print(f"  Новых строк в БД: {new_rows} (ожидается 0)")

# ДАМП
print("\n=== ДАМП DailyTaskSet + DailyTaskItem ===")
dts = DailyTaskSet.query.filter_by(user_id=user.id).first()
if dts:
    print(f"  DailyTaskSet: id={dts.id} user_id={dts.user_id} target_date={dts.target_date}")
    print(f"    status={dts.status} triggered_by={dts.triggered_by} class_level={dts.class_level}")
    for it in DailyTaskItem.query.filter_by(daily_set_id=dts.id).order_by(DailyTaskItem.position).all():
        spec = json.loads(it.gemini_spec_json or '{}')
        print(f"  ITEM id={it.id} pos={it.position}")
        print(f"    slot_kind={it.slot_kind} subject={it.subject} topic={it.topic}")
        print(f"    difficulty_level={it.difficulty_level}")
        print(f"    source (gemini_spec)={spec.get('source','?')}")
        print(f"    task_text[:80]={it.task_text[:80] if it.task_text else 'EMPTY'}")

print("\n=== ФИНАЛЬНЫЙ СТАТУС ===")
dts = DailyTaskSet.query.filter_by(user_id=user.id).first()
if dts:
    items = DailyTaskItem.query.filter_by(daily_set_id=dts.id).all()
    print(f"  STATUS: {dts.status}")
    print(f"  Карточек в HTML: {len(items)}")
else:
    print(f"  STATUS: NO SET (0 карточек)")

print("\nГОТОВО.")
db.session.remove()
