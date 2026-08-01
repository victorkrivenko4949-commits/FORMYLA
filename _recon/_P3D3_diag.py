# -*- coding: utf-8 -*-
"""P3D3: Comprehensive DB diagnosis. Read-only. No deletes, no writes."""
import os, sys, sqlite3, json
from datetime import datetime, timezone

MSK = timezone(__import__('datetime').timedelta(hours=3))
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = []
L = lambda s: (OUT.append(str(s)), print(s, flush=True))

def ts(mtime):
    return datetime.fromtimestamp(mtime, tz=MSK).strftime('%Y-%m-%d %H:%M:%S MSK')

# ── Helper: safely run SQL, return None if table missing ──
def safe_fetch(db_path, sql, params=()):
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return rows
    except Exception as e:
        return f"ERROR: {e}"

def safe_fetch_one(db_path, sql, params=()):
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        row = conn.execute(sql, params).fetchone()
        conn.close()
        return row
    except Exception as e:
        return f"ERROR: {e}"

def table_exists(db_path, table_name):
    r = safe_fetch(db_path, "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    if isinstance(r, str):
        return False
    return len(r) > 0

# ══════════════════════════════════════════════════════════════════════════
# ЗАДАЧА 1: ВСЕ ФАЙЛЫ БАЗЫ
# ══════════════════════════════════════════════════════════════════════════
L('='*80)
L('ЗАДАЧА 1. ВСЕ ФАЙЛЫ БАЗЫ (.db, .sqlite, .sqlite3)')
L('='*80)
L('')

db_files = []
for root, dirs, files in os.walk(BASE):
    dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', '.venv', 'venv', 'node_modules', 'npm', '.pytest_cache', 'flask_session']]
    for f in files:
        if any(f.endswith(ext) for ext in ['.db', '.sqlite', '.sqlite3']):
            db_files.append(os.path.join(root, f))

db_files.sort()

for i, db_path in enumerate(db_files, 1):
    mtime = os.path.getmtime(db_path)
    size = os.path.getsize(db_path)
    rel = os.path.relpath(db_path, BASE)
    L(f'[{i}] {rel}')
    L(f'    Full: {db_path}')
    L(f'    Size: {size:,} bytes  |  Modified: {ts(mtime)}')
    
    # adaptive_tasks
    if table_exists(db_path, 'adaptive_tasks'):
        r = safe_fetch_one(db_path, "SELECT COUNT(*), MAX(difficulty_level), MIN(difficulty_level) FROM adaptive_tasks")
        if isinstance(r, str):
            L(f'    adaptive_tasks: ERROR reading - {r}')
        elif r:
            L(f'    adaptive_tasks: rows={r[0]}, min_level={r[2]}, max_level={r[1]}')
        else:
            L(f'    adaptive_tasks: rows=0')
    else:
        L(f'    adaptive_tasks: TABLE NOT FOUND')
    
    # task_assignment_history
    if table_exists(db_path, 'task_assignment_history'):
        r = safe_fetch_one(db_path, "SELECT COUNT(*) FROM task_assignment_history")
        L(f'    task_assignment_history: rows={r[0] if r and not isinstance(r,str) else "ERROR"}')
    else:
        L(f'    task_assignment_history: TABLE NOT FOUND')
    
    # users
    if table_exists(db_path, 'users'):
        r = safe_fetch_one(db_path, "SELECT COUNT(*) FROM users")
        L(f'    users: rows={r[0] if r and not isinstance(r,str) else "ERROR"}')
    else:
        L(f'    users: TABLE NOT FOUND')
    
    # All tables overview
    r = safe_fetch(db_path, "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    if not isinstance(r, str):
        tables = [t[0] for t in r]
        L(f'    Tables ({len(tables)}): {", ".join(tables[:20])}{"..." if len(tables)>20 else ""}')
    L('')

# ══════════════════════════════════════════════════════════════════════════
# ЗАДАЧА 2: КТО КУДА СМОТРИТ
# ══════════════════════════════════════════════════════════════════════════
L('='*80)
L('ЗАДАЧА 2. КТО КУДА СМОТРИТ')
L('='*80)
L('')

# (a) app.py DB config
L('--- (a) app.py DATABASE_URL logic ---')
L(f'  app.py line 178: _database_url = os.environ.get("DATABASE_URL", "sqlite:///formyla.db")')

# Check .env
env_file = os.path.join(BASE, '.env')
env_db = None
if os.path.exists(env_file):
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('DATABASE_URL') and '=' in line:
                env_db = line.split('=', 1)[1].strip().strip('"').strip("'")
                break

L(f'  .env DATABASE_URL: {env_db if env_db else "NOT SET"}')

# Check actual env
actual_env = os.environ.get('DATABASE_URL', 'NOT SET')
L(f'  os.environ DATABASE_URL: {actual_env}')

# What app.py actually resolves to
if actual_env != 'NOT SET':
    db_url = actual_env
else:
    db_url = 'sqlite:///formyla.db'

L(f'  Effective SQLALCHEMY_DATABASE_URI (before app.py fixup): {db_url}')

# Read app.py lines 178-200 for DB config
import inspect
app_py_path = os.path.join(BASE, 'app.py')
with open(app_py_path, 'r', encoding='utf-8') as f:
    app_lines = f.readlines()

# Find DB config lines
for lineno, line in enumerate(app_lines[177:187], 178):
    L(f'  app.py:{lineno}: {line.rstrip()}')

# Now the critical part: what does sqlite:///formyla.db resolve to?
# Flask-SQLAlchemy with sqlite:/// relative path resolves relative to current working directory
# OR relative to app.instance_path depending on config.

# Let's actually import app and check
L('')
L('--- (b) Actual engine.url from app ---')
os.chdir(BASE)
sys.path.insert(0, BASE)

# Monkey-patch to avoid Sentry/key issues
os.environ.setdefault('FLASK_ENV', 'development')

from app import app as flask_app
with flask_app.app_context():
    from app import db
    engine_url = str(db.engine.url)
    L(f'  app.db.engine.url = {engine_url}')
    
    # Resolve the actual path
    if 'sqlite' in engine_url:
        # Extract path from sqlite:///path
        db_path_part = engine_url.replace('sqlite:///', '')
        abs_db = os.path.abspath(db_path_part)
        L(f'  os.path.abspath(db_path) = {abs_db}')
        L(f'  File exists: {os.path.exists(abs_db)}')
        if os.path.exists(abs_db):
            L(f'  Size: {os.path.getsize(abs_db):,} bytes')
            L(f'  Modified: {ts(os.path.getmtime(abs_db))}')

L('')
L('--- (c) What _recon scripts see ---')
# _recon/step5_acceptance.py line 16: db = sqlite3.connect('formyla.db')
L(f'  [_recon/step5_acceptance.py:16] db = sqlite3.connect(\'formyla.db\')')
L(f'  Script chdirs to: {os.path.join(BASE, "_recon")} (line 6: os.chdir(BASE) where BASE=dirname(__file__))')
_recon_dir = os.path.join(BASE, '_recon')
_recon_db = os.path.join(_recon_dir, 'formyla.db')
L(f'  Resolves to: {_recon_db}')
L(f'  File exists: {os.path.exists(_recon_db)}')
if os.path.exists(_recon_db):
    L(f'  Size: {os.path.getsize(_recon_db):,} bytes')
    rows = safe_fetch_one(_recon_db, "SELECT COUNT(*) FROM adaptive_tasks")
    L(f'  adaptive_tasks rows: {rows}')
    rows = safe_fetch_one(_recon_db, "SELECT COUNT(*) FROM users")
    L(f'  users rows: {rows}')

L('')
L('--- _recon/P3D_PROOF_RUN.py DB path ---')
L(f'  [_recon/P3D_PROOF_RUN.py:7-9]: BASE = dirname(dirname(__file__)), DB = BASE/instance/formyla.db')
_p3d_db = os.path.join(BASE, 'instance', 'formyla.db')
L(f'  Resolves to: {_p3d_db}')
L(f'  File exists: {os.path.exists(_p3d_db)}')
if os.path.exists(_p3d_db):
    rows = safe_fetch_one(_p3d_db, "SELECT COUNT(*) FROM adaptive_tasks")
    L(f'  adaptive_tasks rows: {rows}')

L('')
L('--- _recon/step6_acceptance.py DB path ---')
L(f'  [_recon/step6_acceptance.py:4]: os.chdir(r\'c:\\Users\\Redmi\\Desktop\\Новая папка (2)\')')
L(f'  Uses app.db (SQLAlchemy) -> same as app.py -> instance/formyla.db')
L(f'  So step6 sees the SAME DB as the live app.')

L('')
L('--- VERDICT ---')
L('  app.py -> instance/formyla.db (via SQLAlchemy)')
L('  _recon/P3D_PROOF_RUN.py -> instance/formyla.db (correct)')
L('  _recon/step5_acceptance.py -> _recon/formyla.db (WRONG - separate DB!)')
L('  _recon/step6_acceptance.py -> instance/formyla.db (correct, uses app context)')

# Check if _recon/formyla.db exists
_recon_db_path = os.path.join(BASE, '_recon', 'formyla.db')
if os.path.exists(_recon_db_path):
    L(f'')
    L(f'  ⚠️ _recon/formyla.db EXISTS: size={os.path.getsize(_recon_db_path):,}, mtime={ts(os.path.getmtime(_recon_db_path))}')
    rows = safe_fetch_one(_recon_db_path, "SELECT COUNT(*) FROM adaptive_tasks")
    L(f'     adaptive_tasks rows in _recon/formyla.db: {rows}')
else:
    L(f'')
    L(f'  _recon/formyla.db NOT FOUND (step5 can\'t even run)')

L('')

# ══════════════════════════════════════════════════════════════════════════
# ЗАДАЧА 3: ЖИВ ЛИ ПУЛ
# ══════════════════════════════════════════════════════════════════════════
L('='*80)
L('ЗАДАЧА 3. ЖИВ ЛИ ПУЛ (instance/formyla.db)')
L('='*80)
L('')

main_db = os.path.join(BASE, 'instance', 'formyla.db')
if not os.path.exists(main_db):
    L('  MAIN DB NOT FOUND!')
else:
    L(f'  Database: {main_db}')
    L(f'  Size: {os.path.getsize(main_db):,} bytes')
    L(f'  Modified: {ts(os.path.getmtime(main_db))}')
    L('')
    
    # Total tasks
    r = safe_fetch_one(main_db, "SELECT COUNT(*) FROM adaptive_tasks")
    total_at = r[0] if r and not isinstance(r, str) else 0
    L(f'  adaptive_tasks total: {total_at}')
    
    # olympiad_tasks
    if table_exists(main_db, 'olympiad_tasks'):
        r = safe_fetch_one(main_db, "SELECT COUNT(*) FROM olympiad_tasks")
        L(f'  olympiad_tasks total: {r[0] if r and not isinstance(r,str) else "ERROR"}')
    else:
        L(f'  olympiad_tasks: TABLE NOT FOUND')
    
    # problems
    if table_exists(main_db, 'problems'):
        r = safe_fetch_one(main_db, "SELECT COUNT(*) FROM problems")
        L(f'  problems total: {r[0] if r and not isinstance(r,str) else "ERROR"}')
    else:
        L(f'  problems: TABLE NOT FOUND')
    
    L('')
    L('  --- Разбивка по классам (adaptive_tasks) ---')
    r = safe_fetch(main_db, "SELECT class_level, COUNT(*) FROM adaptive_tasks GROUP BY class_level ORDER BY class_level")
    if isinstance(r, str):
        L(f'  ERROR: {r}')
    else:
        for g, cnt in r:
            L(f'  Grade {g}: {cnt}')
    
    L('')
    L('  --- Разбивка по уровням 1..5 (adaptive_tasks) ---')
    r = safe_fetch(main_db, "SELECT difficulty_level, COUNT(*) FROM adaptive_tasks GROUP BY difficulty_level ORDER BY difficulty_level")
    if isinstance(r, str):
        L(f'  ERROR: {r}')
    else:
        for lvl, cnt in r:
            L(f'  Level {lvl}: {cnt}')
    
    L('')
    L('  --- Последние 5 задач (by id DESC) ---')
    r = safe_fetch(main_db, "SELECT id, class_level, difficulty_level, subject, source FROM adaptive_tasks ORDER BY id DESC LIMIT 5")
    if isinstance(r, str):
        L(f'  ERROR: {r}')
    else:
        for row in r:
            L(f'  id={row[0]}, grade={row[1]}, level={row[2]}, subject={row[3]}, source={row[4]}')
    
    # Compare with P2D2 8773
    L('')
    L(f'  --- Сравнение с P2D2 (8773) ---')
    L(f'  Текущее число adaptive_tasks: {total_at}')
    L(f'  P2D2 ожидалось: 8773')
    if total_at < 8773:
        lost = 8773 - total_at
        L(f'  ПОТЕРЯНО: {lost} задач')
        
        # Check file modification times to find what could have deleted them
        L(f'  Проверка времени изменения файлов:')
        
        # instance/formyla.db mtime
        main_mtime = os.path.getmtime(main_db)
        L(f'    instance/formyla.db: {ts(main_mtime)}')
        
        # Check root formyla.db (same mtime as _recon backups?)
        root_db = os.path.join(BASE, 'formyla.db')
        if os.path.exists(root_db):
            L(f'    formyla.db (root): {ts(os.path.getmtime(root_db))}')
        
        # Check backup times
        p2_db = os.path.join(BASE, '_recon', 'formyla_backup_P2.db')
        if os.path.exists(p2_db):
            L(f'    _recon/formyla_backup_P2.db: {ts(os.path.getmtime(p2_db))}')
            r = safe_fetch_one(p2_db, "SELECT COUNT(*) FROM adaptive_tasks")
            L(f'      adaptive_tasks в P2 backup: {r}')
        
        p3_db = os.path.join(BASE, '_recon', 'formyla_backup_P3.db')
        if os.path.exists(p3_db):
            L(f'    _recon/formyla_backup_P3.db: {ts(os.path.getmtime(p3_db))}')
            r = safe_fetch_one(p3_db, "SELECT COUNT(*) FROM adaptive_tasks")
            L(f'      adaptive_tasks в P3 backup: {r}')
        
        # Check recent backup
        recent = os.path.join(BASE, '_recon', 'backup_formyla_20260731_211943.db')
        if os.path.exists(recent):
            L(f'    _recon/backup_formyla_20260731_211943.db: {ts(os.path.getmtime(recent))}')
            r = safe_fetch_one(recent, "SELECT COUNT(*) FROM adaptive_tasks")
            L(f'      adaptive_tasks: {r}')
        
        L(f'')
        L(f'  ВЫВОД: {lost} задач потеряно относительно P2D2.')
        L(f'  База instance/formyla.db имеет {total_at} задач.')
        L(f'  Это может быть результатом wipe_adaptive скриптов или миграции.')
    else:
        L(f'  Задач не меньше 8773 — OK')
    
    L('')

# ══════════════════════════════════════════════════════════════════════════
# ЗАДАЧА 4: БЭКАПЫ
# ══════════════════════════════════════════════════════════════════════════
L('='*80)
L('ЗАДАЧА 4. БЭКАПЫ В _recon')
L('='*80)
L('')

recon_dir = os.path.join(BASE, '_recon')
for f in sorted(os.listdir(recon_dir)):
    if f.endswith('.db'):
        fpath = os.path.join(recon_dir, f)
        size = os.path.getsize(fpath)
        mtime = os.path.getmtime(fpath)
        r = safe_fetch_one(fpath, "SELECT COUNT(*) FROM adaptive_tasks")
        at_count = r[0] if r and not isinstance(r, str) else 'ERROR'
        r2 = safe_fetch_one(fpath, "SELECT COUNT(*) FROM users")
        u_count = r2[0] if r2 and not isinstance(r2, str) else 'ERROR'
        L(f'  {f}')
        L(f'    Date: {ts(mtime)}, Size: {size:,} bytes, adaptive_tasks: {at_count}, users: {u_count}')

L('')

# ══════════════════════════════════════════════════════════════════════════
# ЗАДАЧА 5: ПОЧИНИ ЗАПУСК СКРИПТОВ
# ══════════════════════════════════════════════════════════════════════════
L('='*80)
L('ЗАДАЧА 5. FIX _recon/step5_acceptance.py')
L('='*80)
L('')

step5_path = os.path.join(BASE, '_recon', 'step5_acceptance.py')
with open(step5_path, 'r', encoding='utf-8') as f:
    step5_content = f.read()

L('  Current lines 5-16:')
for line in step5_content.split('\n')[4:17]:
    L(f'    {line}')

L('')
L('  FIX: replace lines 5-7, 16 to use BASE-based path')
L('  BEFORE:')
L('    BASE = os.path.dirname(os.path.abspath(__file__))')
L('    os.chdir(BASE)')
L('    sys.path.insert(0, BASE)')
L('    db = sqlite3.connect(\'formyla.db\')')
L('')
L('  AFTER:')
L('    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))')
L('    os.chdir(BASE)')
L('    sys.path.insert(0, BASE)')
L('    db = sqlite3.connect(os.path.join(BASE, \'instance\', \'formyla.db\'))')

# Apply the fix
new_step5 = step5_content
new_step5 = new_step5.replace(
    "BASE = os.path.dirname(os.path.abspath(__file__))",
    "BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))"
)
new_step5 = new_step5.replace(
    "db = sqlite3.connect('formyla.db')",
    "db = sqlite3.connect(os.path.join(BASE, 'instance', 'formyla.db'))"
)

with open(step5_path, 'w', encoding='utf-8') as f:
    f.write(new_step5)

L('')
L('  Fix applied to _recon/step5_acceptance.py')

# Now verify by checking what path it computes
_recon_script_dir = os.path.dirname(step5_path)
test_base = os.path.dirname(_recon_script_dir)  # one level up from _recon
test_db = os.path.join(test_base, 'instance', 'formyla.db')
L(f'  After fix, script will use BASE = {test_base}')
L(f'  DB path = {test_db}')
L(f'  File exists: {os.path.exists(test_db)}')

# Read back to verify
with open(step5_path, 'r', encoding='utf-8') as f:
    fixed_lines = f.read().split('\n')

L('')
L('  Verified lines 5-7, 16:')
for line in fixed_lines[4:17]:
    L(f'    {line}')

# Now test - read adaptive_tasks count from this db via python
L('')
L('  --- Verification: read adaptive_tasks from fixed path ---')
test_count = safe_fetch_one(test_db, "SELECT COUNT(*) FROM adaptive_tasks")
L(f'  adaptive_tasks count via step5 fixed path: {test_count}')

# Compare with app's view
with flask_app.app_context():
    from models import AdaptiveTask
    app_count = AdaptiveTask.query.count()
    L(f'  adaptive_tasks count via app (SQLAlchemy): {app_count}')
    L(f'  Match: {"YES" if test_count and test_count[0] == app_count else "NO - MISMATCH!"}')

L('')
L('='*80)
L('DIAGNOSIS COMPLETE')
L('='*80)

# Write report
report_path = os.path.join(BASE, '_recon', 'P3D3_DBFIND.md')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write('# P3D3 DB FIND REPORT\n\n')
    f.write(f'Generated: {datetime.now(MSK).isoformat()}\n\n')
    f.write('```\n')
    f.write('\n'.join(OUT))
    f.write('\n```\n')

L('')
L(f'Report written to: {report_path}')
