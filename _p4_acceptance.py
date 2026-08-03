# -*- coding: utf-8 -*-
"""P4 DEBT acceptance — 7 сценариев."""
import sys, os, json, re
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from models import db, User
from models_curator import CuratorState
from daily_tasks.models import DailyTaskSet, DailyTaskItem
from services.daily_task_rotation import pick_daily_set
from services.daily_debt import refresh_debt_for_user, get_debt_items, get_debt_count, migrate_to_debt

ctx = app.app_context()
ctx.push()

# ── helpers ──────────────────────────────────────────────────────────
def make_user(email, nickname, grade=9):
    u = User.query.filter_by(email=email).first()
    if not u:
        u = User(email=email, nickname=nickname, name=nickname, preferred_grade=grade)
        db.session.add(u)
        db.session.commit()
    # очистить старые данные
    for dts in DailyTaskSet.query.filter_by(user_id=u.id).all():
        DailyTaskItem.query.filter_by(daily_set_id=dts.id).delete()
        db.session.delete(dts)
    cs = CuratorState.query.filter_by(user_id=u.id).first()
    if cs: db.session.delete(cs)
    db.session.commit()
    cs = CuratorState(user_id=u.id)
    cs.prep_state = {'onboarding': {'daily_tasks': 5, 'route_ceiling': 5, 'grade': grade, 'target_level': 3}}
    cs.level_mu = 2.0
    cs.level_sigma = 1.5
    cs.level_by_section = '{}'
    cs.onboarding_done = True
    db.session.add(cs)
    db.session.commit()
    return u

def simulate_day(user, day_offset, solve_count=0):
    """Симулировать день: выдать набор, решить solve_count задач."""
    # удаляем старые сеты
    for dts in DailyTaskSet.query.filter_by(user_id=user.id).all():
        DailyTaskItem.query.filter_by(daily_set_id=dts.id).delete()
        db.session.delete(dts)
    db.session.commit()

    # меняем target_date сетов вручную (как будто они с прошлых дней)
    # но pick_daily_set создаёт сегодняшний — нам нужно симулировать прошлые дни
    # ПОДХОД: создаём сет напрямую через pick_daily_set, потом вручную меняем дату
    result = pick_daily_set(user.id, force_regenerate=True)
    tasks = result.get('tasks', [])

    # меняем target_date всех сетов и debt
    dts = DailyTaskSet.query.filter_by(user_id=user.id).first()
    past = date.today() - timedelta(days=day_offset)
    if dts:
        dts.target_date = past
        db.session.commit()

    # Если решаем часть — помечаем первые solve_count как отвеченные
    items = DailyTaskItem.query.filter_by(daily_set_id=dts.id).order_by(DailyTaskItem.position).all()
    for i, it in enumerate(items):
        if i < solve_count:
            it.user_answer = 'ok'
            it.is_correct = True
        else:
            it.user_answer = None
            it.is_correct = None
    db.session.commit()

    # Мигрируем нерешённое в долг
    refresh_debt_for_user(user.id)

    return {
        'date': past.isoformat(),
        'issued': len(tasks),
        'solved': solve_count,
        'debt_count': get_debt_count(user.id),
    }

# ── СЦЕНАРИЙ 1: день 1 решить 2 из 5, день 2 показать долг ────────────
print("=" * 60)
print("СЦЕНАРИЙ 1: День 1 — решил 2 из 5, День 2 — показ долга")
u1 = make_user('p4_s1@test.ru', 'p4_s1')

d1 = simulate_day(u1, day_offset=1, solve_count=2)
print(f"  День 1 ({d1['date']}): выдано {d1['issued']}, решено {d1['solved']}, в долге {d1['debt_count']}")

# День 2: симулируем новый день
for dts in DailyTaskSet.query.filter_by(user_id=u1.id).all():
    DailyTaskItem.query.filter_by(daily_set_id=dts.id).delete()
    db.session.delete(dts)
db.session.commit()

# Мигрируем вчерашнее в долг перед новым днём
refresh_debt_for_user(u1.id)
debt_before = get_debt_count(u1.id)
print(f"  День 2 до выдачи: в долге {debt_before}")

d2 = simulate_day(u1, day_offset=0, solve_count=0)
dts = DailyTaskSet.query.filter_by(user_id=u1.id).first()
today_items = DailyTaskItem.query.filter_by(daily_set_id=dts.id).count() if dts else 0
debt_after = get_debt_count(u1.id)
print(f"  День 2 ({d2['date']}): выдано {d2['issued']}, в долге {debt_after}")
print(f"  Сегодняшний набор: {today_items} задач (должен = 5, а не 5 - {debt_before})")
assert today_items == 5, f"FAIL: сегодняшний набор {today_items}, ожидалось 5 (независимо от долга)"

# ── СЦЕНАРИЙ 2: накопление 5 дней без решений ────────────────────────
print("\n" + "=" * 60)
print("СЦЕНАРИЙ 2: 5 дней подряд не решает ничего")
u2 = make_user('p4_s2@test.ru', 'p4_s2')

for offset in range(5, 0, -1):
    d = simulate_day(u2, day_offset=offset, solve_count=0)
    print(f"  День -{offset} ({d['date']}): выдано {d['issued']}, в долге {d['debt_count']}")

# День сегодня: подтверждаем, что новый набор полный
for dts in DailyTaskSet.query.filter_by(user_id=u2.id).all():
    DailyTaskItem.query.filter_by(daily_set_id=dts.id).delete()
    db.session.delete(dts)
db.session.commit()
refresh_debt_for_user(u2.id)
d_today = simulate_day(u2, day_offset=0, solve_count=0)
dts = DailyTaskSet.query.filter_by(user_id=u2.id).first()
today_items = DailyTaskItem.query.filter_by(daily_set_id=dts.id).count() if dts else 0
print(f"  Сегодня ({d_today['date']}): выдано {d_today['issued']}, в долге {d_today['debt_count']}, сегодняшний набор {today_items}")
assert today_items == 5, f"FAIL: набор {today_items} вместо 5"

# ── СЦЕНАРИЙ 3: сгорание на 8-й день ──────────────────────────────────
print("\n" + "=" * 60)
print("СЦЕНАРИЙ 3: сгорание на 8-й день")
u3 = make_user('p4_s3@test.ru', 'p4_s3')

# День 1: задача
simulate_day(u3, day_offset=8, solve_count=0)
dts = DailyTaskSet.query.filter_by(user_id=u3.id).first()
items = DailyTaskItem.query.filter_by(daily_set_id=dts.id).all()
print(f"  День -8: выдано {len(items)}, в долге {get_debt_count(u3.id)}")
# Принудительно ставим debt для этого сета
for it in items:
    it.debt_status = 'active'
    it.debt_until = (date.today() - timedelta(days=8)) + timedelta(days=7)  # вчера сгорело
db.session.commit()

# День 7 (debt_until = сегодня - 1)
refresh_debt_for_user(u3.id)
d7 = get_debt_count(u3.id)
from services.level_engine import get_state
mu_before = get_state(u3.id)['mu']
print(f"  День 7: в долге {d7}")

# День 8 (debt_until < today -> burned)
# Меняем debt_until так, чтобы оно было сегодня-1
for it in items:
    it.debt_until = date.today() - timedelta(days=1)
db.session.commit()
refresh_debt_for_user(u3.id)
d8 = get_debt_count(u3.id)
mu_after = get_state(u3.id)['mu']
print(f"  День 8: в долге {d8}, mu до={mu_before:.3f} после={mu_after:.3f} (должно быть равно)")

# День 9
refresh_debt_for_user(u3.id)
d9 = get_debt_count(u3.id)
print(f"  День 9: в долге {d9}")
assert d7 > 0, f"FAIL: день 7 долг должен быть > 0, а он {d7}"
assert d8 == 0, f"FAIL: день 8 долг должен быть 0, а он {d8}"
assert abs(mu_before - mu_after) < 0.001, f"FAIL: mu изменился: {mu_before} -> {mu_after}"

# ── СЦЕНАРИЙ 4: test_client через редиректы ──────────────────────────
print("\n" + "=" * 60)
print("СЦЕНАРИЙ 4: test_client через редиректы")
# Берём u2 (у него долг)
client = app.test_client()
with client.session_transaction() as sess:
    sess['_user_id'] = str(u2.id)
    sess['_fresh'] = True

# /daily-set -> 302 -> /daily_tasks
r = client.get('/daily-set')
print(f"  GET /daily-set: {r.status_code}")
r = client.get('/daily_tasks', follow_redirects=True)
print(f"  GET /daily_tasks (follow): {r.status_code}")
html = r.data.decode('utf-8')

debt_block = 'dt-debt-block' in html
print(f"  Блок долга в HTML: {debt_block}")

debt_count_html = html.count('dt-debt-item')
print(f"  Карточек долга в HTML: {debt_count_html}")

today_items_html = html.count('data-task-id')
print(f"  Карточек сегодняшнего набора: {today_items_html}")

# Заголовки с датами
date_headers = re.findall(r'dt-debt-group-date">([^<]+)', html)
print(f"  Заголовки дат в долге: {date_headers}")

fragment = re.search(r'<div class="dt-debt-block">.*?</div>\s*</div>\s*</div>', html, re.DOTALL)
if fragment:
    print(f"\n  ФРАГМЕНТ HTML блока долга:\n{fragment.group()[:600]}")
else:
    print("  ФРАГМЕНТ: NOT FOUND")

# ── СЦЕНАРИЙ 5: ученик без долга ─────────────────────────────────────
print("\n" + "=" * 60)
print("СЦЕНАРИЙ 5: ученик без долга")
u5 = make_user('p4_s5@test.ru', 'p4_s5')
# очищаем всё
for dts in DailyTaskSet.query.filter_by(user_id=u5.id).all():
    DailyTaskItem.query.filter_by(daily_set_id=dts.id).delete()
    db.session.delete(dts)
db.session.commit()
simulate_day(u5, day_offset=0, solve_count=5)  # решил всё

with client.session_transaction() as sess:
    sess['_user_id'] = str(u5.id)
    sess['_fresh'] = True
r = client.get('/daily_tasks', follow_redirects=True)
html5 = r.data.decode('utf-8')
debt_block_5 = 'dt-debt-block' in html5
print(f"  Блок долга: {debt_block_5} (должен быть False)")

# ── СЦЕНАРИЙ 6: повторный запуск сгорания ────────────────────────────
print("\n" + "=" * 60)
print("СЦЕНАРИЙ 6: повторный запуск сгорания")
# Используем u3 (уже сгорело)
pre_burn = get_debt_count(u3.id)
burn_stale = __import__('services.daily_debt').burn_stale_debt
n1 = burn_stale(u3.id)
n2 = burn_stale(u3.id)
post_burn = get_debt_count(u3.id)
print(f"  До: {pre_burn}, сгорело 1-й раз: {n1}, 2-й раз: {n2}, после: {post_burn}")
assert n1 == n2 == 0, f"FAIL: повторное сгорание {n1}/{n2}"

# ── СЦЕНАРИЙ 7: pytest ───────────────────────────────────────────────
print("\n" + "=" * 60)
print("СЦЕНАРИЙ 7: запуск pytest")
import subprocess
r = subprocess.run(
    [sys.executable, '-m', 'pytest', 'tests/', '-q', '--tb=no'],
    cwd=os.path.dirname(__file__),
    capture_output=True, text=True, timeout=300
)
out = r.stdout + r.stderr
# Найти строку с итогами
for line in out.split('\n'):
    if 'passed' in line or 'failed' in line or 'error' in line:
        print(f"  {line.strip()}")
print(f"\n  Exit: {r.returncode}")

print("\nГОТОВО.")
db.session.remove()
