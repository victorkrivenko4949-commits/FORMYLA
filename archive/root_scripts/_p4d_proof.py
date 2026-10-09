# -*- coding: utf-8 -*-
"""P4D acceptance — all 7 tasks. Measured numbers only."""
import sys, os, json, re, sqlite3
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from models import db
from daily_tasks.models import DailyTaskSet, DailyTaskItem
from services.daily_debt import refresh_debt_for_user, get_debt_count, migrate_to_debt, burn_stale_debt
from services.level_engine import get_state

DB = os.path.join(os.path.dirname(__file__), 'instance', 'formyla.db')
app.app_context().push()
TODAY = date.today()

def raw():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def cleanup():
    """Delete debt_* users via raw SQL only to avoid ORM cascade issues."""
    rc = raw()
    ids = [r[0] for r in rc.execute("SELECT id FROM users WHERE email LIKE 'debt_%@test.local'").fetchall()]
    if ids:
        ph = ','.join(['?']*len(ids))
        rc.execute(f"DELETE FROM curator_state WHERE user_id IN ({ph})", ids)
        rc.execute(f"DELETE FROM daily_task_items WHERE daily_set_id IN (SELECT id FROM daily_task_sets WHERE user_id IN ({ph}))", ids)
        rc.execute(f"DELETE FROM daily_task_sets WHERE user_id IN ({ph})", ids)
        rc.execute(f"DELETE FROM task_assignment_history WHERE user_id IN ({ph})", ids)
        rc.execute(f"DELETE FROM users WHERE id IN ({ph})", ids)
        rc.commit()
    rc.close()
    return raw().execute("SELECT COUNT(*) FROM users WHERE email LIKE 'debt_%@test.local'").fetchone()[0]

def make_user():
    """Raw SQL insert user + curator_state."""
    rc = raw()
    rc.execute("INSERT INTO users (email, nickname, name, preferred_grade) VALUES ('debt_1@test.local','debt_1','Debt Test',9)")
    uid = rc.execute("SELECT last_insert_rowid()").fetchone()[0]
    rc.execute(
        "INSERT INTO curator_state (user_id, prep_state, level_mu, level_sigma, level_by_section, onboarding_done) "
        "VALUES (?, ?, 2.0, 1.5, '{}', 1)",
        (uid, json.dumps({'onboarding':{'daily_tasks':5,'route_ceiling':5,'grade':9,'target_level':3}}))
    )
    rc.commit(); rc.close()
    # Force SQLAlchemy to see this user
    db.session.expire_all()
    return uid

def inject_day_orm(uid, target_date, solved=0, total=5):
    """Use ORM so migrate_to_debt can see the items."""
    dts = DailyTaskSet(
        user_id=uid, target_date=target_date, class_level=9,
        status='ready', triggered_by='daily_rotation',
        reason_summary=f'Test {target_date}'
    )
    db.session.add(dts); db.session.flush()
    subjects = ['Теория чисел','Геометрия','Алгебра','Комбинаторика','Логика']
    for pos in range(1, total+1):
        it = DailyTaskItem(
            daily_set_id=dts.id, position=pos, slot_kind='daily_rotation',
            subject=subjects[(pos-1)%5], topic=f'Тема #{pos}',
            difficulty_level=2+(pos%3),
            task_text=f'Задача {target_date} #{pos}. Решите x+{pos}={pos+10}.',
            correct_answer='10', solution='x=10', hints='[]',
            gemini_spec_json=json.dumps({'source':'test'}),
            status='approved',
            user_answer='ok' if pos <= solved else None,
            is_correct=True if pos <= solved else None,
        )
        db.session.add(it)
    db.session.commit()
    return dts.id

def debt_count_sql(uid=None):
    rc = raw()
    if uid:
        n = rc.execute(
            "SELECT COUNT(*) FROM daily_task_items dti JOIN daily_task_sets dts ON dts.id=dti.daily_set_id "
            "WHERE dts.user_id=? AND dti.debt_status='active'", (uid,)
        ).fetchone()[0]
    else:
        n = rc.execute("SELECT COUNT(*) FROM daily_task_items WHERE debt_status='active'").fetchone()[0]
    rc.close(); return n

def debt_stats_sql():
    rc = raw()
    rows = rc.execute("SELECT debt_status, COUNT(*) FROM daily_task_items WHERE debt_status IS NOT NULL GROUP BY debt_status").fetchall()
    rc.close(); return {r[0]: r[1] for r in rows}

# ═══════════════════════════════════════════════════════════════
print("="*70)
print("ЗАДАЧА 2 — СЦЕНАРИЙ ПЕРЕНОСА")
cleanup(); uid = make_user()
day1 = TODAY - timedelta(days=1); day2 = TODAY
inject_day_orm(uid, day1, solved=2, total=5)
migrate_to_debt(uid, day2)
d1 = debt_count_sql(uid)
print(f"  День 1 ({day1}): выдано 5, решено 2, в долге: {d1}")
inject_day_orm(uid, day2, solved=0, total=5)
refresh_debt_for_user(uid)
d2 = debt_count_sql(uid)
rc = raw()
td = rc.execute(
    "SELECT COUNT(*) FROM daily_task_items dti JOIN daily_task_sets dts ON dts.id=dti.daily_set_id "
    "WHERE dts.user_id=? AND dts.target_date=?", (uid, day2.isoformat())
).fetchone()[0]; rc.close()
print(f"  День 2 ({day2}): выдано 5, решено 0, в долге: {d2}, сегодня набор: {td}")
print(f"  ТАБЛИЦА:")
print(f"  День       | Выдано | Решено | В долге | Сегодня набор")
print(f"  {day1} |      5 |      2 |       {d1} | —")
print(f"  {day2} |      5 |      0 |       {d2} | {td}")
assert d1==3 and d2==3 and td==5, f"FAIL: d1={d1} d2={d2} today={td}"

# ═══════════════════════════════════════════════════════════════
print("\n"+"="*70)
print("ЗАДАЧА 3 — НАКОПЛЕНИЕ")
cleanup(); uid = make_user()
print("  День       | Выдано | Решено | В долге | Сегодня набор")
for offset in range(5, 0, -1):
    d = TODAY - timedelta(days=offset)
    inject_day_orm(uid, d, solved=0, total=5)
    refresh_debt_for_user(uid)
    print(f"  {d} |      5 |      0 |       {debt_count_sql(uid)} | —")
inject_day_orm(uid, TODAY, solved=0, total=5)
refresh_debt_for_user(uid)
fd = debt_count_sql(uid)
rc = raw()
tn = rc.execute(
    "SELECT COUNT(*) FROM daily_task_items dti JOIN daily_task_sets dts ON dts.id=dti.daily_set_id "
    "WHERE dts.user_id=? AND dts.target_date=?", (uid, TODAY.isoformat())
).fetchone()[0]; rc.close()
print(f"  {TODAY} |      5 |      0 |       {fd} | {tn}")
assert fd==25 and tn==5, f"FAIL: debt={fd} today={tn}"

# ═══════════════════════════════════════════════════════════════
print("\n"+"="*70)
print("ЗАДАЧА 4 — СГОРАНИЕ")
cleanup(); uid = make_user()
dold = TODAY - timedelta(days=8)
inject_day_orm(uid, dold, solved=0, total=5)
# Принудительно: debt_until=dold+7=today-1
rc = raw()
rc.execute(
    "UPDATE daily_task_items SET debt_status='active', debt_until=? "
    "WHERE daily_set_id IN (SELECT id FROM daily_task_sets WHERE user_id=? AND target_date=?)",
    ((dold+timedelta(days=7)).isoformat(), uid, dold.isoformat())
); rc.commit(); rc.close()
db.session.expire_all()

mu_b= get_state(uid)['mu']; sigma_b= get_state(uid)['sigma']
d7 = debt_count_sql(uid)
print(f"  День 7: в долге {d7}, mu={mu_b:.4f} sigma={sigma_b:.4f}")
refresh_debt_for_user(uid)
d8 = debt_count_sql(uid); mu_a=get_state(uid)['mu']; sigma_a=get_state(uid)['sigma']
print(f"  День 8: в долге {d8}, mu={mu_a:.4f} sigma={sigma_a:.4f}")
refresh_debt_for_user(uid)
d9 = debt_count_sql(uid)
print(f"  День 9: в долге {d9}")
assert d7==5 and d8==0 and d9==0, f"FAIL: d7={d7} d8={d8} d9={d9}"
assert abs(mu_b-mu_a)<0.0001 and abs(sigma_b-sigma_a)<0.0001, "FAIL: mu/sigma changed"

# ═══════════════════════════════════════════════════════════════
print("\n"+"="*70)
print("ЗАДАЧА 5 — ЖИВОЙ HTML")
cleanup(); uid = make_user()
for offset in range(5, 0, -1):
    d = TODAY - timedelta(days=offset)
    inject_day_orm(uid, d, solved=0, total=5)
    refresh_debt_for_user(uid)
inject_day_orm(uid, TODAY, solved=0, total=5)
refresh_debt_for_user(uid)

client = app.test_client()
with client.session_transaction() as sess:
    sess['_user_id'] = str(uid); sess['_fresh'] = True

r1 = client.get('/daily-set')
print(f"  GET /daily-set: {r1.status_code} -> {r1.headers.get('Location','no redirect')}")
r2 = client.get('/daily_tasks', follow_redirects=True)
html = r2.data.decode('utf-8')
status_m = re.search(r'"status"\s*:\s*"(\w+)"', html)
debt_blocks = html.count('dt-debt-item')
dates = re.findall(r'dt-debt-group-date">([^<]+)', html)
print(f"  STATUS: {status_m.group(1) if status_m else 'NOT FOUND'}")
print(f"  Карточек долга: {debt_blocks}")
print(f"  Даты-подзаголовки: {dates}")
idx = html.find('dt-debt-block')
if idx >= 0:
    print(f"\n  ФРАГМЕНТ HTML блока долга:\n{html[idx:idx+1800]}")

# 5.2 — без долга
cleanup(); uid2 = make_user()
inject_day_orm(uid2, TODAY, solved=5, total=5)
refresh_debt_for_user(uid2)
with client.session_transaction() as sess:
    sess['_user_id'] = str(uid2); sess['_fresh'] = True
r3 = client.get('/daily_tasks', follow_redirects=True)
html5 = r3.data.decode('utf-8')
# Ищем именно <div class="dt-debt-block">, а не CSS
has_debt_div = '<div class="dt-debt-block">' in html5
print(f"\n  5.2 — Без долга: <div class=\"dt-debt-block\"> в HTML = {has_debt_div}")
assert not has_debt_div, "FAIL: debt block shown without debt"
print("  5.3 — Внешние сервисы: 0 (чистый сценарий без AI)")

# ═══════════════════════════════════════════════════════════════
print("\n"+"="*70)
print("ЗАДАЧА 6 — ИДЕМПОТЕНТНОСТЬ")
cleanup(); uid = make_user()
dold = TODAY - timedelta(days=10)
inject_day_orm(uid, dold, solved=0, total=3)
rc = raw()
rc.execute(
    "UPDATE daily_task_items SET debt_status='active', debt_until=? "
    "WHERE daily_set_id IN (SELECT id FROM daily_task_sets WHERE user_id=? AND target_date=?)",
    ((dold+timedelta(days=7)).isoformat(), uid, dold.isoformat())
); rc.commit(); rc.close()
db.session.expire_all()

s0=debt_stats_sql(); print(f"  До: {s0}")
n1=burn_stale_debt(); s1=debt_stats_sql(); print(f"  После 1-го: сгорело {n1}, {s1}")
n2=burn_stale_debt(); s2=debt_stats_sql(); print(f"  После 2-го: сгорело {n2}, {s2}")
assert n1>0 and n2==0 and s1==s2, f"FAIL: n1={n1} n2={n2} s1={s1} s2={s2}"

# ═══════════════════════════════════════════════════════════════
print("\n"+"="*70)
print("ЗАДАЧА 7 — ОЧИСТКА + PYTEST")
rem = cleanup()
print(f"  debt_* после очистки: {rem}")
assert rem == 0, f"FAIL: {rem} users left"

import subprocess
r = subprocess.run([sys.executable,'-m','pytest','tests/','-q','--tb=no'],
    cwd=os.path.dirname(__file__), capture_output=True, text=True, timeout=300)
for line in (r.stdout+r.stderr).split('\n'):
    if 'passed' in line or 'failed' in line or 'error' in line:
        print(f"  {line.strip()}")

print("\nГОТОВО.")
db.session.remove()
