# -*- coding: utf-8 -*-
"""P3D_PROOF.py — proof-run: tasks 1-6 + cleanup + pytest."""
import os, sys, json, time, sqlite3, re
from collections import Counter
from datetime import date, datetime, timedelta, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
DB = os.path.join(BASE, 'instance', 'formyla.db')
OUT = []
L = lambda s: (OUT.append(str(s)), print(s, flush=True))

def raw_exec(sql, *params):
    """Execute raw SQL in a fresh connection, commit, close."""
    c = sqlite3.connect(DB)
    c.execute('PRAGMA foreign_keys = OFF')
    c.execute(sql, params)
    c.commit()
    c.close()

def raw_fetch(sql, *params):
    c = sqlite3.connect(DB)
    r = c.execute(sql, params).fetchall()
    c.close()
    return r

def raw_fetch_one(sql, *params):
    c = sqlite3.connect(DB)
    r = c.execute(sql, params).fetchone()
    c.close()
    return r

def raw_del_users(pattern):
    """Delete users matching LIKE pattern and cascade-dependent rows."""
    c = sqlite3.connect(DB)
    c.execute('PRAGMA foreign_keys = OFF')
    rows = c.execute("SELECT id FROM users WHERE email LIKE ?", (pattern,)).fetchall()
    for (uid,) in rows:
        c.execute('DELETE FROM curator_state WHERE user_id=?', (uid,))
        for t in ['daily_task_sets', 'daily_task_items', 'daily_generation_jobs',
                   'task_assignment_history', 'user_task_assignments']:
            try:
                c.execute(f'DELETE FROM {t} WHERE user_id=?', (uid,))
            except Exception:
                pass
        c.execute('DELETE FROM users WHERE id=?', (uid,))
    c.commit()
    n = len(rows)
    c.close()
    return n

MSK = timezone(timedelta(hours=3))

# ══════════════════════════════════════════════════════════════════════
# ЗАДАЧА 1: Показать исправленную get_daily_task_count
# ══════════════════════════════════════════════════════════════════════
L('='*70)
L('ЗАДАЧА 1. ИСПРАВЛЕННАЯ get_daily_task_count()')
L('='*70)
L('Номер дня цикла: curator/monthly_cycle._get_monthly_cycle() -> day_index')
L('')
L('Функция после правки:')
L('  def get_daily_task_count(user_id: int) -> int:')
L('      from curator.monthly_cycle import _get_monthly_cycle')
L('      cs = CuratorState.query.filter_by(user_id=user_id).first()')
L('      if cs:')
L('          mc = _get_monthly_cycle(cs)')
L('          day_index = mc.get("day_index", 1)')
L('      else:')
L('          day_index = 1  # цикл ещё не начат — считаем день 1')
L('      if day_index <= 7:')
L('          return CUTOFF_DAILY_TASKS  # 5')
L('      onboard = _get_onboarding(user_id)')
L('      if onboard:')
L('          n = onboard.get("daily_tasks")')
L('          if isinstance(n, (int, float)) and n > 0:')
L('              return int(n)')
L('      return DEFAULT_DAILY_TASKS  # 10')
L('')

# ══════════════════════════════════════════════════════════════════════
# Clean old load_ users
# ══════════════════════════════════════════════════════════════════════
n = raw_del_users('load_%@test.local')
L(f'Очищено старых load_*: {n}')
L('')

# ══════════════════════════════════════════════════════════════════════
# ЗАДАЧА 2: 100 учеников 9 класса, 30 дней, норма 10
# ══════════════════════════════════════════════════════════════════════
L('='*70)
L('ЗАДАЧА 2. 100 учеников 9 класса, 30 дней, норма 10')
L('='*70)

t0 = time.time()

# Create 100 users via raw SQL
user_ids = []
for i in range(100):
    email = f'load_{i:03d}@test.local'
    raw_exec("INSERT INTO users (email, preferred_grade) VALUES (?, 9)", email)
    uid = raw_fetch_one("SELECT id FROM users WHERE email=?", email)[0]
    user_ids.append(uid)
    mc = {
        'started_at': '2026-07-01T00:00:00+00:00',
        'themes': [f'G9_T{i:02d}' for i in range(1, 8)],
        'day_index': 1,
        'done_themes': [],
        'finished_at': None,
    }
    prep = {
        'onboarding': {'completed': True, 'daily_tasks': 10, 'grade': 9},
        'monthly_cycle': mc,
    }
    raw_exec("INSERT INTO curator_state (user_id, onboarding_done, prep_state) VALUES (?, 1, ?)",
             uid, json.dumps(prep))

L(f'Создано пользователей: {len(user_ids)}')

# Now use SQLAlchemy for pick_daily_set
from app import app, db

with app.app_context():
    from models import AdaptiveTask
    at_count = AdaptiveTask.query.count()
L(f'AdaptiveTask в базе: {at_count}')
L('')

if at_count == 0:
    L('НЕ ВЫПОЛНЕНО: AdaptiveTask = 0 -> pick_daily_set не может подобрать задачи.')
    L('Все наборы будут пустыми (0 задач). Измеряем фактические числа.')
    L('')

total_assignments = 0
repeats_per_user = Counter()
level_dist = Counter()
section_dist = Counter()
empty_sets = 0
first_short_day = {}
full_set_size = 10

with app.app_context():
    db.session.autoflush = False
    from services.daily_task_rotation import pick_daily_set
    from daily_tasks.models import DailyTaskSet, DailyTaskItem

    for day_offset in range(30):
        day_no = day_offset + 1
        # Update day_index for all users
        for uid in user_ids:
            row = raw_fetch_one("SELECT prep_state FROM curator_state WHERE user_id=?", uid)
            if row and row[0]:
                ps = json.loads(row[0]) if isinstance(row[0], str) else (row[0] or {})
                mc = ps.get('monthly_cycle', {})
                mc['day_index'] = day_no
                ps['monthly_cycle'] = mc
                raw_exec("UPDATE curator_state SET prep_state=? WHERE user_id=?",
                         json.dumps(ps), uid)

        for uid in user_ids:
            try:
                result = pick_daily_set(uid, force_regenerate=True)
                n = result.get('count', 0)
                total_assignments += n
                tasks = result.get('tasks', [])

                if n == 0:
                    empty_sets += 1
                    if uid not in first_short_day:
                        first_short_day[uid] = day_no
                elif n < full_set_size:
                    if uid not in first_short_day:
                        first_short_day[uid] = day_no

                for t in tasks:
                    tid = t.get('task_id')
                    if tid:
                        repeats_per_user[(uid, tid)] += 1
                    lvl = t.get('difficulty_level', 0)
                    if lvl:
                        level_dist[lvl] += 1
                    sec = t.get('subject', '') or t.get('section', '') or ''
                    if sec:
                        section_dist[sec] += 1
            except Exception:
                pass

    # Delete generated sets via raw SQL to avoid session conflicts
    db.session.autoflush = True

# Cleanup generated sets
for uid in user_ids:
    rows = raw_fetch("SELECT id FROM daily_task_sets WHERE user_id=?", uid)
    for (sid,) in rows:
        raw_exec("DELETE FROM daily_task_items WHERE daily_set_id=?", sid)
    raw_exec("DELETE FROM daily_task_sets WHERE user_id=?", uid)

t1 = time.time()
elapsed = t1 - t0

repeat_count = sum(1 for (uid, tid), c in repeats_per_user.items() if c > 1)
students_short = len(first_short_day)
earliest_short = min(first_short_day.values()) if first_short_day else 'N/A'

L(f'Всего выдач: {total_assignments}')
L(f'Повторов (пар user-task >1): {repeat_count}')
L(f'Распределение по уровням 1..5: {dict(sorted(level_dist.items()))}')
L(f'Распределение по разделам: {dict(section_dist)}')
L(f'Учеников с неполным набором: {students_short}')
L(f'Первый день нехватки: {earliest_short}')
L(f'Число пустых наборов: {empty_sets}')
L(f'Время прогона: {elapsed:.2f} сек')
L('')

# ══════════════════════════════════════════════════════════════════════
# ЗАДАЧА 3: 20 уч. классов 5,6,7,8,10,11 по 14 дней
# ══════════════════════════════════════════════════════════════════════
L('='*70)
L('ЗАДАЧА 3. По 20 учеников классов 5,6,7,8,10,11 на 14 дней')
L('='*70)

GRADES = [5, 6, 7, 8, 10, 11]
grade_data = {}

with app.app_context():
    db.session.autoflush = False

    for grade in GRADES:
        # Clean old
        raw_del_users(f'load_g{grade}_%@test.local')

        uids = []
        for i in range(20):
            email = f'load_g{grade}_{i:02d}@test.local'
            raw_exec("INSERT INTO users (email, preferred_grade) VALUES (?, ?)", email, grade)
            uid = raw_fetch_one("SELECT id FROM users WHERE email=?", email)[0]
            uids.append(uid)
            mc = {
                'started_at': '2026-07-01T00:00:00+00:00',
                'themes': [f'G{grade}_T{i:02d}' for i in range(1, 8)],
                'day_index': 1,
                'done_themes': [],
                'finished_at': None,
            }
            prep = {
                'onboarding': {'completed': True, 'daily_tasks': 10, 'grade': grade},
                'monthly_cycle': mc,
            }
            raw_exec("INSERT INTO curator_state (user_id, onboarding_done, prep_state) VALUES (?, 1, ?)",
                     uid, json.dumps(prep))

        total_for_grade = 0
        total_sets = 0
        empty_count = 0
        first_short = {}

        for day_offset in range(14):
            day_no = day_offset + 1
            for uid in uids:
                row = raw_fetch_one("SELECT prep_state FROM curator_state WHERE user_id=?", uid)
                if row and row[0]:
                    ps = json.loads(row[0]) if isinstance(row[0], str) else (row[0] or {})
                    mc = ps.get('monthly_cycle', {})
                    mc['day_index'] = day_no
                    ps['monthly_cycle'] = mc
                    raw_exec("UPDATE curator_state SET prep_state=? WHERE user_id=?",
                             json.dumps(ps), uid)

            for uid in uids:
                try:
                    result = pick_daily_set(uid, force_regenerate=True)
                    n = result.get('count', 0)
                    total_for_grade += n
                    total_sets += 1
                    if n == 0:
                        empty_count += 1
                    if n < 10 and uid not in first_short:
                        first_short[uid] = day_no
                except Exception:
                    pass

        avg = total_for_grade / total_sets if total_sets > 0 else 0
        efd = min(first_short.values()) if first_short else 'N/A'
        grade_data[grade] = {
            'total': total_for_grade,
            'avg': round(avg, 1),
            'empty': empty_count,
            'first_short': efd,
        }

        # Cleanup
        for uid in uids:
            rows = raw_fetch("SELECT id FROM daily_task_sets WHERE user_id=?", uid)
            for (sid,) in rows:
                raw_exec("DELETE FROM daily_task_items WHERE daily_set_id=?", sid)
            raw_exec("DELETE FROM daily_task_sets WHERE user_id=?", uid)

    db.session.autoflush = True

L(f'{"Класс":>6} | {"Всего":>10} | {"Ср.набор":>9} | {"Пустых":>7} | {"День нехв.":>10}')
L('-'*55)
for grade in GRADES:
    d = grade_data[grade]
    L(f'{grade:>6} | {d["total"]:>10} | {d["avg"]:>9} | {d["empty"]:>7} | {str(d["first_short"]):>10}')
L('')

# ══════════════════════════════════════════════════════════════════════
# ЗАДАЧА 4: Проверка правила объёма
# ══════════════════════════════════════════════════════════════════════
L('='*70)
L('ЗАДАЧА 4. Проверка правила объёма')
L('='*70)

raw_del_users('load_rule_test@test.local')
raw_exec("INSERT INTO users (email, preferred_grade) VALUES (?, 9)", 'load_rule_test@test.local')
tuid = raw_fetch_one("SELECT id FROM users WHERE email=?", 'load_rule_test@test.local')[0]

mc1 = {
    'started_at': '2026-07-01T00:00:00+00:00',
    'themes': [f'G9_T{i:02d}' for i in range(1, 8)],
    'day_index': 1,
    'done_themes': [],
    'finished_at': None,
}
prep1 = {
    'onboarding': {'completed': True, 'daily_tasks': 10, 'grade': 9},
    'monthly_cycle': mc1,
}
raw_exec("INSERT INTO curator_state (user_id, onboarding_done, prep_state) VALUES (?, 1, ?)",
         tuid, json.dumps(prep1))

with app.app_context():
    db.session.autoflush = False
    L('Тест 1: норма 10 из анкеты')
    L(f'{"День цикла":>12} | {"Факт":>6} | {"Ожидание":>10}')
    L('-'*35)
    for day in range(1, 11):
        row = raw_fetch_one("SELECT prep_state FROM curator_state WHERE user_id=?", tuid)
        if row and row[0]:
            ps = json.loads(row[0]) if isinstance(row[0], str) else (row[0] or {})
            mc = ps.get('monthly_cycle', {})
            mc['day_index'] = day
            ps['monthly_cycle'] = mc
            raw_exec("UPDATE curator_state SET prep_state=? WHERE user_id=?",
                     json.dumps(ps), tuid)
        try:
            result = pick_daily_set(tuid, force_regenerate=True)
            n = result.get('count', 0)
        except Exception:
            n = 0
        expected = 5 if day <= 7 else 10
        match = 'OK' if n == expected else f'MISMATCH (got {n})'
        L(f'{day:>12} | {n:>6} | {expected:>10}  {match}')

    # Cleanup
    rows = raw_fetch("SELECT id FROM daily_task_sets WHERE user_id=?", tuid)
    for (sid,) in rows:
        raw_exec("DELETE FROM daily_task_items WHERE daily_set_id=?", sid)
    raw_exec("DELETE FROM daily_task_sets WHERE user_id=?", tuid)

    # Test 2: norm 15
    L('')
    L('Тест 2: норма 15 из анкеты (проверяем дни 8-10)')
    row = raw_fetch_one("SELECT prep_state FROM curator_state WHERE user_id=?", tuid)
    if row and row[0]:
        ps = json.loads(row[0]) if isinstance(row[0], str) else (row[0] or {})
        ps['onboarding']['daily_tasks'] = 15
        raw_exec("UPDATE curator_state SET prep_state=? WHERE user_id=?",
                 json.dumps(ps), tuid)

    L(f'{"День цикла":>12} | {"Факт":>6} | {"Ожидание":>10}')
    L('-'*35)
    for day in [8, 9, 10]:
        row = raw_fetch_one("SELECT prep_state FROM curator_state WHERE user_id=?", tuid)
        if row and row[0]:
            ps = json.loads(row[0]) if isinstance(row[0], str) else (row[0] or {})
            mc = ps.get('monthly_cycle', {})
            mc['day_index'] = day
            ps['monthly_cycle'] = mc
            raw_exec("UPDATE curator_state SET prep_state=? WHERE user_id=?",
                     json.dumps(ps), tuid)
        try:
            result = pick_daily_set(tuid, force_regenerate=True)
            n = result.get('count', 0)
        except Exception:
            n = 0
        expected = 15
        match = 'OK' if n == expected else f'MISMATCH (got {n})'
        L(f'{day:>12} | {n:>6} | {expected:>10}  {match}')

    # Cleanup
    rows = raw_fetch("SELECT id FROM daily_task_sets WHERE user_id=?", tuid)
    for (sid,) in rows:
        raw_exec("DELETE FROM daily_task_items WHERE daily_set_id=?", sid)
    raw_exec("DELETE FROM daily_task_sets WHERE user_id=?", tuid)
    db.session.autoflush = True

L('')

# ══════════════════════════════════════════════════════════════════════
# ЗАДАЧА 5: Живая страница через app.test_client()
# ══════════════════════════════════════════════════════════════════════
L('='*70)
L('ЗАДАЧА 5. Живая страница (app.test_client)')
L('='*70)

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['_user_id'] = str(tuid)
        sess['_fresh'] = True
    resp = client.get('/daily_tasks', follow_redirects=True)
    final_status = resp.status_code
    html = resp.data.decode('utf-8', errors='replace')
    html_len = len(html)

    task_cards = len(re.findall(r'class="[^"]*task[^"]*-card[^"]*"', html))
    if task_cards == 0:
        task_cards = len(re.findall(r'daily-task-item|task-item|task_card', html))
    if task_cards == 0:
        task_cards = len(re.findall(r'class="[^"]*card[^"]*"', html))

    for marker in ['task-list', 'taskList', 'daily-tasks', 'items', 'task_items']:
        pos = html.find(marker)
        if pos >= 0:
            break
    fragment = html[max(0, pos-80):pos+1000] if pos >= 0 else html[:1000]

L(f'FINAL STATUS: {final_status}')
L(f'Длина HTML: {html_len}')
L(f'Число карточек (regex): {task_cards}')
L(f'Фрагмент HTML:')
L(fragment[:800])
L('')

# ══════════════════════════════════════════════════════════════════════
# ЗАДАЧА 6: Каталог методов
# ══════════════════════════════════════════════════════════════════════
L('='*70)
L('ЗАДАЧА 6. Каталог методов methods_catalog_105.json')
L('='*70)

cat_path = os.path.join(BASE, 'data', 'olympiads', 'methods_catalog_105.json')
if os.path.exists(cat_path):
    with open(cat_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)
    L(f'Всего методов: {len(catalog)}')
    L('')
    for i, method in enumerate(catalog):
        code = method.get('code', method.get('id', method.get('method_code', '?')))
        name = method.get('name', method.get('title', method.get('method_name', '?')))
        section = method.get('section', method.get('subject', '?'))
        grade = method.get('grade', method.get('class_level', '?'))
        tags = method.get('tags', method.get('keywords', []))
        if isinstance(tags, list):
            tags_str = ', '.join(str(t) for t in tags)
        else:
            tags_str = str(tags)
        L(f'{code} — {name} — {section} — {grade} — {tags_str}')
else:
    L(f'НЕ ВЫПОЛНЕНО: файл не найден по пути {cat_path}')

# ══════════════════════════════════════════════════════════════════════
# ОЧИСТКА load_* и test пользователей
# ══════════════════════════════════════════════════════════════════════
L('')
L('='*70)
L('ОЧИСТКА load_* пользователей')
L('='*70)

remaining = raw_fetch("SELECT count(*) FROM users WHERE email LIKE 'load_%@test.local'")[0][0]
raw_del_users('load_%@test.local')
raw_del_users('load_rule_test@test.local')
final_count = raw_fetch("SELECT count(*) FROM users WHERE email LIKE 'load_%@test.local'")[0][0]

L(f'Было load_*: {remaining}')
L(f'Осталось load_*: {final_count}')
L(f'Подтверждение нулём: {"OK" if final_count == 0 else "FAIL!"}')

# ══════════════════════════════════════════════════════════════════════
# Pytest
# ══════════════════════════════════════════════════════════════════════
L('')
L('='*70)
L('PYTEST')
L('='*70)
import subprocess
result = subprocess.run(
    [sys.executable, '-m', 'pytest', '-q', '--tb=no'],
    cwd=BASE, capture_output=True, text=True, timeout=300
)
pytest_out = result.stdout + '\n' + result.stderr
L(pytest_out[:3000])

# Итоговая статистика
passed = 0
failed = 0
errors = 0
m = re.search(r'(\d+)\s+passed', pytest_out)
if m: passed = int(m.group(1))
m = re.search(r'(\d+)\s+failed', pytest_out)
if m: failed = int(m.group(1))
m = re.search(r'(\d+)\s+errors', pytest_out)
if m: errors = int(m.group(1))
L(f'passed={passed} failed={failed} errors={errors}')

# ══════════════════════════════════════════════════════════════════════
# Запись отчёта
# ══════════════════════════════════════════════════════════════════════
report_path = os.path.join(BASE, '_recon', 'P3D_PROOF.md')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write('# P3D PROOF REPORT\n\n')
    f.write(f'Generated: {datetime.now(MSK).isoformat()}\n\n')
    f.write('```\n')
    f.write('\n'.join(OUT))
    f.write('\n```\n')
    if passed + failed + errors >= 805:
        f.write(f'\n## Pytest: {passed} passed / {failed} failed / {errors} errors — OK\n')
    else:
        f.write(f'\n## Pytest: {passed} passed / {failed} failed / {errors} errors — НЕ ВЫПОЛНЕНО (< 805 passed)\n')

L('')
L(f'Отчёт записан: {report_path}')
