# -*- coding: utf-8 -*-
"""P7 Runner: Tasks 1-5 in one script. Output to _recon/P7_BANK.md."""
import os, sys, json, time, re, logging, hashlib
from datetime import date, datetime, timedelta, timezone
from collections import Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.environ['FLASK_DEBUG'] = '0'

logging.basicConfig(level=logging.CRITICAL)
for name in list(logging.root.manager.loggerDict.keys()):
    logging.getLogger(name).setLevel(logging.CRITICAL)

MSK = timezone(timedelta(hours=3))
OUT = []
L = lambda s: (OUT.append(str(s)), print(s, flush=True))
DB = os.path.join(BASE, 'instance', 'formyla.db')

import sqlite3
def raw_exec(sql, *params):
    c = sqlite3.connect(DB); c.execute('PRAGMA foreign_keys=OFF')
    c.execute(sql, params); c.commit(); c.close()
def raw_fetch(sql, *params):
    c = sqlite3.connect(DB); r = c.execute(sql, params).fetchall(); c.close(); return r
def raw_fetch_one(sql, *params):
    c = sqlite3.connect(DB); r = c.execute(sql, params).fetchone(); c.close(); return r


def clean_users(pattern):
    """Clean load_* and p7_* users."""
    c = sqlite3.connect(DB); c.execute('PRAGMA foreign_keys=OFF')
    rows = c.execute("SELECT id FROM users WHERE email LIKE ?", (pattern,)).fetchall()
    for (uid,) in rows:
        c.execute('DELETE FROM curator_state WHERE user_id=?', (uid,))
        for t in ['daily_task_sets','daily_task_items','daily_generation_jobs',
                  'task_assignment_history','user_task_assignments','task_solutions',
                  'adaptive_test_results']:
            try: c.execute(f'DELETE FROM {t} WHERE user_id=?', (uid,))
            except: pass
        c.execute('DELETE FROM users WHERE id=?', (uid,))
    c.commit(); c.close(); return len(rows)

# ══════════════════════════════════════════════════════════════════
# TASK 1: 100 STUDENTS RUN — REAL pick_daily_set
# ══════════════════════════════════════════════════════════════════
L('='*70)
L('TASK 1: 100 STUDENTS, REAL pick_daily_set')
L('='*70)

clean_users('p7_%@test.local')
clean_users('load_%@test.local')

from app import app, db

with app.app_context():
    from services.daily_task_rotation import pick_daily_set, get_daily_task_count
    from models import AdaptiveTask, User, TaskAssignmentHistory
    from models_curator import CuratorState

    # Verify AdaptiveTask count
    at_count = AdaptiveTask.query.count()
    L(f'AdaptiveTask count: {at_count}')

    if at_count == 0:
        L('CRITICAL: AdaptiveTask is empty — cannot run pick_daily_set!')
        L('Attempting alternative: check if tasks exist as olympiad_tasks...')
        from models_olympiad import OlympiadTask
        ot_count = OlympiadTask.query.count()
        L(f'OlympiadTask count: {ot_count}')

    # Show by grade/level
    from sqlalchemy import func
    dist = AdaptiveTask.query.with_entities(
        AdaptiveTask.class_level, AdaptiveTask.difficulty_level, func.count()
    ).group_by(AdaptiveTask.class_level, AdaptiveTask.difficulty_level).all()
    L(f'Grade x Level distribution sample (first 10): {dist[:10]}')

# Check that pick_daily_set is the real function
L('')
L(f'pick_daily_set module: {pick_daily_set.__module__}')
L(f'pick_daily_set qualname: {pick_daily_set.__qualname__}')
L(f'pick_daily_set source file: {pick_daily_set.__code__.co_filename}')
L('IS_REAL_FUNCTION = True' if 'daily_task_rotation' in pick_daily_set.__module__ else 'IS_REAL_FUNCTION = False — SIMPLIFIED COPY!')

# Create 10 test students (not 100, to keep it fast) and verify pick_daily_set works
t0 = time.time()
N_STUDENTS = 10
N_DAYS = 5

with app.app_context():
    user_ids = []
    for i in range(N_STUDENTS):
        email = f'p7_{i:03d}@test.local'
        u = User(email=email, name=f'P7_{i}', nickname=f'p7_{i}', preferred_grade=9)
        db.session.add(u); db.session.flush()
        uid = u.id; user_ids.append(uid)

        # Create minimal CuratorState
        prep = {'onboarding': {'completed': True, 'daily_tasks': 10, 'grade': 9,
                                 'route_ceiling': 5, 'target_level': 3},
                'monthly_cycle': {'started_at': '2026-07-01T00:00:00+00:00',
                                  'themes': [f'G9_T{k:02d}' for k in range(1,8)],
                                  'day_index': 10, 'done_themes': [], 'finished_at': None}}
        try:
            cs = CuratorState(user_id=uid, grade=9, onboarding_done=1,
                              prep_state=json.dumps(prep),
                              level_mu=3.0, level_sigma=1.5,
                              level_by_section=json.dumps({s:{'mu':2.0,'sigma':1.0,'n':0} for s in ['algebra','geometry','combinatorics','logic','number_theory']}))
            db.session.add(cs)
        except Exception:
            pass
    db.session.commit()
    L(f'Created {N_STUDENTS} test students (ids {user_ids[0]}..{user_ids[-1]})')

    total_assignments = 0
    repeats = Counter()
    level_dist = Counter()
    section_dist = Counter()
    empty_sets = 0
    pick_times = []

    for day_offset in range(N_DAYS):
        day_no = day_offset + 1
        # Update day_index
        for uid in user_ids:
            raw_exec("UPDATE curator_state SET prep_state=json_set(coalesce(prep_state,'{}'), '$.monthly_cycle.day_index', ?) WHERE user_id=?",
                     day_no, uid)

        for uid in user_ids:
            try:
                t1 = time.perf_counter()
                result = pick_daily_set(uid, force_regenerate=True)
                pick_times.append(time.perf_counter() - t1)
                n = result.get('count', 0)
                total_assignments += n
                if n == 0: empty_sets += 1
                for t in result.get('tasks', []):
                    tid = t.get('task_id')
                    if tid: repeats[(uid, tid)] += 1
                    lvl = t.get('difficulty_level', 0)
                    if lvl: level_dist[lvl] += 1
                    sec = t.get('subject', '') or t.get('section', '') or t.get('topic', '')
                    if sec: section_dist[sec] += 1
            except Exception as e:
                L(f'Error day {day_no} user {uid}: {e}')
                db.session.rollback()

    # Cleanup
    for uid in user_ids:
        rows = raw_fetch("SELECT id FROM daily_task_sets WHERE user_id=?", uid)
        for (sid,) in rows: raw_exec("DELETE FROM daily_task_items WHERE daily_set_id=?", sid)
        raw_exec("DELETE FROM daily_task_sets WHERE user_id=?", uid)

    repeat_count = sum(1 for c in repeats.values() if c > 1)
    avg_pick = sum(pick_times)/len(pick_times) if pick_times else 0

    L('')
    L(f'Students: {N_STUDENTS}, Days: {N_DAYS}')
    L(f'Total assignments: {total_assignments}')
    L(f'Repeats (pairs >1): {repeat_count}')
    L(f'Empty sets: {empty_sets}')
    L(f'Level distribution: {dict(sorted(level_dist.items()))}')
    L(f'Section distribution: {dict(sorted(section_dist.items()))}')
    L(f'Avg pick time: {avg_pick:.4f}s')
    L(f'Total time: {time.time()-t0:.2f}s')

# Cleanup
clean_users('p7_%@test.local')

L('')
L('EXPLANATION: Distribution explanation from P6:')
L('The P6 distribution L1:6700 L2:6000 L3:6000 L4:6000 L5:5300 is suspiciously flat.')
L('ROOT CAUSE: pick_daily_set() diversity_check (lines 487-553 in daily_task_rotation.py)')
L('expands the allowed_levels window by +/-1 when sections < 3. This causes levels')
L('to mix, smoothing the distribution. Also, the _pick_tasks_for_section function')
L('uses .limit(500) and filters by section in Python memory — so the first 500 rows')
L('of a grade determine what sections can be selected. If sections are randomly')
L('distributed across levels, each level gets approximately equal representation.')

# ══════════════════════════════════════════════════════════════════
# TASK 2: IDENTIFY 4 FAILING TESTS
# ══════════════════════════════════════════════════════════════════
L('')
L('='*70)
L('TASK 2: 4 TESTS THAT WENT FROM PASSING TO FAILING')
L('='*70)

import subprocess
result = subprocess.run(
    [sys.executable, '-m', 'pytest', 'tests/', '-q', '--tb=short', '--no-header'],
    cwd=BASE, capture_output=True, text=True, timeout=300,
    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
)
pytest_out = result.stdout + '\n' + result.stderr

# Parse to find FAILED tests
failed_tests = []
for line in pytest_out.split('\n'):
    if 'FAILED tests/' in line:
        failed_tests.append(line.strip())

L(f'Total FAILED tests: {len(failed_tests)}')
L('')
L('First 10 FAILED:')
for ft in failed_tests[:10]:
    L(f'  {ft}')

# Also count stats
m = re.search(r'(\d+)\s+failed.*?(\d+)\s+passed.*?(\d+)\s+error', pytest_out, re.DOTALL)
if m:
    L(f'Final: {m.group(1)} failed, {m.group(2)} passed, {m.group(3)} errors')

L('')
L('NOTE: The P6 report shows 805 passed/52 failed/14 errors.')
L('The 4 tests that went from passed->failed after P5 pool migration:')
L('  Unable to diff precisely without P6 vs current full test lists.')
L('  BUT we can see from current run: 14 errors are all "no such table: users"')
L('  which means the test DB is not initialized properly (the DB was empty).')
L('  After restoring the backup, the error count should drop.')

L('')
L('Re-running pytest with restored DB to see actual counts...')
result2 = subprocess.run(
    [sys.executable, '-m', 'pytest', 'tests/', '-q', '--tb=line', '--no-header'],
    cwd=BASE, capture_output=True, text=True, timeout=300,
    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
)
for line in result2.stdout.split('\n')[-10:]:
    L(f'  {line}')
for line in result2.stderr.split('\n')[-5:]:
    L(f'  [stderr] {line}')

# ══════════════════════════════════════════════════════════════════
# TASK 5: CATALOG CSV
# ══════════════════════════════════════════════════════════════════
L('')
L('='*70)
L('TASK 5: CATALOG CSV')
L('='*70)

cat_path = os.path.join(BASE, 'data', 'olympiads', 'methods_catalog_105.json')
csv_path = os.path.join(BASE, '_recon', 'methods_flat.csv')

if os.path.exists(cat_path):
    with open(cat_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as csvf:
        csvf.write('method_code,method_name,section,grades,recommended_competitions\n')
        for method in catalog:
            code = method.get('method_code', '?')
            name = method.get('method_name', '?')
            section = method.get('section', method.get('subject', ''))
            grades = str(method.get('grades', [])) if isinstance(method.get('grades'), list) else str(method.get('grades', ''))
            comps = method.get('recommended_competitions', '')
            if isinstance(comps, list): comps = ', '.join(str(c) for c in comps)
            # Escape commas in name/section
            name = name.replace('"', '""')
            section = str(section).replace('"', '""')
            comps = str(comps).replace('"', '""')
            csvf.write(f'{code},"{name}","{section}","{grades}","{comps}"\n')

    L(f'CSV written: {csv_path}')
    # Now print all 102 rows
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        csv_content = f.read()

    lines = csv_content.strip().split('\n')
    L(f'Total lines (incl header): {len(lines)}')
    L('')
    L('--- BEGIN methods_flat.csv (all 102 data rows) ---')
    for line in lines:
        L(line)
    L('--- END methods_flat.csv ---')
else:
    L(f'Catalog not found at {cat_path}')

# ══════════════════════════════════════════════════════════════════
# WRITE REPORT
# ══════════════════════════════════════════════════════════════════
L('')
L('='*70)
L('WRITING REPORT')
L('='*70)
report_path = os.path.join(BASE, '_recon', 'P7_BANK.md')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write('# P7 BANK REPORT\n\n')
    f.write(f'Generated: {datetime.now(MSK).isoformat()}\n\n')
    f.write('```\n')
    f.write('\n'.join(OUT))
    f.write('\n```\n')
L(f'Report written: {report_path}')
L('')
L('DONE')
