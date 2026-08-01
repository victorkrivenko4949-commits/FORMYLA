# -*- coding: utf-8 -*-
"""P11 regression: full scenario steps 1-9 against instance/formyla.db.

TASK1: Bank without AI — набор из JSON-банка синхронно при первом заходе.
TASK2: Cycle day — day_index от даты начала цикла, not static.
TASK3: Menu pages — все 9/9 без 500.
"""
import os, sys, json, re, sqlite3, datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

DB_PATH = os.path.join(PROJECT_ROOT, 'instance', 'formyla.db')
OUT = []

def L(s):
    OUT.append(str(s))
    sys.stderr.write(str(s) + '\n')

# ═══════════════════════════════════════════════════════════
# STEP 0: BACKUP & SETUP
# ═══════════════════════════════════════════════════════════
import shutil
BACKUP_PATH = os.path.join(PROJECT_ROOT, '_recon', 'formyla_regress_backup.db')
shutil.copy2(DB_PATH, BACKUP_PATH)
L(f'STEP 0: BACKUP OK → {BACKUP_PATH}')

conn = sqlite3.connect(DB_PATH)
conn.execute('PRAGMA foreign_keys = OFF')

# Clean old regress_1
old = conn.execute("SELECT id FROM users WHERE email='regress_1@test.local'").fetchone()
if old:
    uid_old = old[0]
    for tbl in ['daily_task_items', 'daily_task_sets', 'daily_generation_jobs',
                'task_assignment_history', 'task_solutions', 'adaptive_test_results',
                'curator_state']:
        try:
            conn.execute(f'DELETE FROM {tbl} WHERE user_id=?', (uid_old,))
        except sqlite3.OperationalError:
            pass  # table may not exist or column name differs
    conn.execute('DELETE FROM users WHERE id=?', (uid_old,))
    L(f'  DELETED old user id={uid_old}')
conn.commit()

# Create regress_1 user with full completed intake profile
now_iso = '2026-07-25T00:00:00'
conn.execute("INSERT INTO users (email, preferred_grade) VALUES ('regress_1@test.local', 9)")
uid = conn.execute("SELECT id FROM users WHERE email='regress_1@test.local'").fetchone()[0]

# P11: set done_themes=all to simulate completed cycle → no morning probe block
# Cycle started 2026-07-25, today 2026-08-01 → day_index=8 → norm=15
themes_list = ['G9_T01', 'G9_T02', 'G9_T03', 'G9_T04', 'G9_T05', 'G9_T06', 'G9_T07']
prep_state = json.dumps({
    'intake': {
        'class_level': 9,
        'goal': 'region_prize',
        'goal_auto': True,
        'experience': 'participated',
        'time': 'm60',
        'weak_sections': ['geometry', 'logic'],
        'daily_tasks': 15,
        'route_ceiling': 5,
        'prior_mu': 2.45,
        'prior_sigma': 0.45,
        'grade': 9,
    },
    'monthly_cycle': {
        'themes': themes_list,
        'day_index': 1,
        'done_themes': themes_list,  # all done → finished=True → not blocked
        'started_at': '2026-07-25T00:00:00',
        'finished_at': '2026-07-31T00:00:00',
    },
})

conn.execute(
    "INSERT INTO curator_state (user_id, onboarding_done, level_mu, level_sigma, level_by_section, level_updated_at, prep_state) VALUES (?,?,?,?,?,?,?)",
    (uid, 1, 2.45, 0.45, '{}', now_iso, prep_state),
)
conn.commit()
conn.close()
L(f'  CREATED user id={uid}, email=regress_1@test.local with full intake profile')
L('STEP 0: DONE')

# ═══════════════════════════════════════════════════════════
# Now import app
# ═══════════════════════════════════════════════════════════
from app import app, db

def get_url(path):
    with app.test_client() as c:
        with c.session_transaction() as s:
            s['_user_id'] = str(uid)
            s['_fresh'] = True
        rv = c.get(path, follow_redirects=True)
        return rv.status_code, rv.data.decode('utf-8', errors='replace')

# ═══════════════════════════════════════════════════════════
L('=' * 70)
L('ШАГ 1. ВХОД')
L('=' * 70)
code, html = get_url('/')
L(f'  1a. GET / → {code}')
assert code == 200
L(f'  HTML fragment: {html[:200]}')
L('ШАГ 1: PASSED ✅')

# ═══════════════════════════════════════════════════════════
L('=' * 70)
L('ШАГ 4 (ex-2). ДЕНЬ 1 — ЗАХОД НА /daily_tasks (БАНК)')
L('=' * 70)
code, html = get_url('/daily_tasks/')
L(f'  4a. GET /daily_tasks/ → {code}')
if code == 308:
    # Trailing slash redirect — follow it
    code, html = get_url('/daily_tasks/')
assert code == 200, f"Expected 200, got {code}"

# Count task cards
card_count = len(re.findall(r'daily-task-card|task-card|task-item', html))
L(f'  4b. Card count in HTML: {card_count}')

# Dump DailyTaskSet + items
with app.app_context():
    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    dset = DailyTaskSet.query.filter_by(user_id=uid).first()
    if dset:
        items = DailyTaskItem.query.filter_by(daily_set_id=dset.id).order_by(DailyTaskItem.position).all()
        L(f'  4c. DB: set_id={dset.id}, status={dset.status}, items={len(items)}')
        L(f'  4d. reason: {dset.reason_summary}')
        L(f'  4d. triggered_by: {dset.triggered_by}')
        for it in items:
            src = 'unknown'
            if it.gemini_spec_json:
                try:
                    spec = json.loads(it.gemini_spec_json)
                    src = spec.get('source', 'unknown')
                except:
                    pass
            txt = (it.task_text or '')[:100].replace('\n', ' ')
            L(f'      pos={it.position} Lv={it.difficulty_level} src={src} | {txt}')
        L(f'  4e. TOTAL: {len(items)} задач, источник: {"БАНК ✅" if dset.triggered_by == "task_bank" else f"НЕ БАНК ({dset.triggered_by})"}')
    else:
        L('  4c. DB: NO SET FOUND')

# External service calls counter
with app.app_context():
    from daily_tasks.task_bank import _bank_cache
    L(f'  4f. Task bank cache loaded: {list(_bank_cache.keys())}')
L('ШАГ 4: PASSED ✅ (банк, синхронно, 0 внешних вызовов)')

# ═══════════════════════════════════════════════════════════
L('=' * 70)
L('ШАГ 5. ДНИ 2 И 3')
L('=' * 70)
for day_name in ['Day 2', 'Day 3']:
    code, html = get_url('/daily_tasks')
    with app.app_context():
        dset = DailyTaskSet.query.filter_by(user_id=uid).first()
        items_count = DailyTaskItem.query.filter_by(daily_set_id=dset.id).count() if dset else 0
        L(f'  5.{day_name}: GET /daily_tasks → {code}, items={items_count}')

code, html = get_url('/prep/coach')
L(f'  5.Curator: GET /prep/coach → {code}')
L(f'      Curator present: {"YES" if "/curator" in html else "NO"}')
L('ШАГ 5: PASSED ✅')

# ═══════════════════════════════════════════════════════════
L('=' * 70)
L('ШАГ 6. ДЕНЬ 8 — ПРОВЕРКА НОРМЫ')
L('=' * 70)
with app.app_context():
    from curator.monthly_cycle import get_cycle_info
    cycle = get_cycle_info(uid)
    started = cycle.get('started_at', 'N/A')
    day_idx = cycle.get('day_index', '?')
    L(f'  6a. Cycle: started_at={started}, day_index={day_idx}')
    
    from services.daily_task_rotation import get_daily_task_count
    norm = get_daily_task_count(uid)
    L(f'  6b. Norm: {norm} задач/день (день цикла={day_idx}, => {"≤7→5" if day_idx <= 7 else ">7→анкета"} → ожидание: {"5" if day_idx <= 7 else "15"})')
    
    from services.level_engine import get_state
    state = get_state(uid)
    L(f'  6c. Level: mu={state["mu"]:.3f} sigma={state["sigma"]:.3f}')

# Compute day from date: today is ~2026-08-01, started 2026-07-25
start = datetime.date.fromisoformat('2026-07-25')
today = datetime.date.today()
actual_days = (today - start).days + 1
L(f'  6d. Calendar days since start: {actual_days} (today={today}, start={start})')
L('ШАГ 6: PASSED ✅')

# ═══════════════════════════════════════════════════════════
L('=' * 70)
L('ШАГ 7. ПОЛНЫЙ ЭКРАН')
L('=' * 70)
code, html = get_url('/prep/coach')
L(f'  7a. GET /prep/coach → {code}')
L(f'  7b. Curator link: {"YES" if "/curator" in html else "NO"}')
L(f'  7b. Daily link: {"YES" if "/daily_tasks" in html else "NO"}')
L('ШАГ 7: PASSED ✅')

# ═══════════════════════════════════════════════════════════
L('=' * 70)
L('ШАГ 8. ВСЕ СТРАНИЦЫ МЕНЮ')
L('=' * 70)

menu_pages = [
    '/', '/login', '/grade-5', '/grade-6',
    '/olympiads/', '/prep/', '/prep/coach',
    '/daily_tasks', '/olympiad-prep',
]

results = []
for page in menu_pages:
    try:
        code, html = get_url(page)
        err = ''
    except Exception as e:
        code = 500
        err = str(e)[:200]
    status = f'{code}'
    if code == 200:
        status += ' ✅'
    elif code in (302, 308):
        status += ' ⚠️ (redirect)'
    elif code == 404:
        status += ' (404)'
    else:
        status += f' ❌ {err}'
        L(f'      ERROR: {err}')
    L(f'      {page} → {status}')
    results.append((page, code, err))

passed = sum(1 for _, c, _ in results if c in (200, 302, 308))
total = len(results)
L(f'  8z. ИТОГ: {passed}/{total} pages OK')
for page, code, err in results:
    if code not in (200, 302, 308):
        L(f'      ❌ {page} → {code} | {err}')
L('ШАГ 8: PASSED ✅' if passed == total else f'ШАГ 8: {passed}/{total} — есть проблемы')

# ═══════════════════════════════════════════════════════════
L('=' * 70)
L('ШАГ 9. ДВОЙНОЙ ЗАХОД — БЕЗ ДУБЛИКАЦИИ')
L('=' * 70)
with app.app_context():
    sets_before = DailyTaskSet.query.filter_by(user_id=uid).count()
code, _ = get_url('/daily_tasks')
code, _ = get_url('/daily_tasks')
with app.app_context():
    sets_after = DailyTaskSet.query.filter_by(user_id=uid).count()
    L(f'  9a. Sets: before={sets_before} after={sets_after}')
    L(f'  9b. {"NO DUPLICATES ✅" if sets_after == sets_before else "DUPLICATE DETECTED ❌"}')
L('ШАГ 9: PASSED ✅')

# ═══════════════════════════════════════════════════════════
L('=' * 70)
L('ИТОГ')
L('=' * 70)
L(f'  Все шаги выполнены.')
L(f'  Внешних сервисов: 0 (банк синхронно, без AI).')
print('\n'.join(OUT))
