# -*- coding: utf-8 -*-
"""Step 5 acceptance tests."""
import sqlite3, os, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
sys.path.insert(0, BASE)

# ---------------------------------------------------------------
# 5.1: DB min/max + out-of-range check
# ---------------------------------------------------------------
print("=" * 60)
print("5.1: DB check - min/max difficulty_level, outside 1..5")
print("=" * 60)

db = sqlite3.connect(os.path.join(BASE, 'instance', 'formyla.db'))
cur = db.cursor()
cur.execute('SELECT MIN(difficulty_level), MAX(difficulty_level) FROM adaptive_tasks')
mn, mx = cur.fetchone()
print(f"  MIN={mn} MAX={mx}")
cur.execute('SELECT COUNT(*) FROM adaptive_tasks WHERE difficulty_level < 1 OR difficulty_level > 5')
outside = cur.fetchone()[0]
print(f"  Outside 1..5: {outside} (expected 0)")

# ---------------------------------------------------------------
# 5.2: grade x level 1..5 with allowed_difficulty() before/after
# ---------------------------------------------------------------
print()
print("=" * 60)
print("5.2: grade x level availability (via allowed_difficulty)")
print("=" * 60)

from app import app as flask_app
from services.level_engine import allowed_difficulty

SOURCE = 'formyla_L1_L5_TOP5'

print(f"\n{'Grade':>7} {'Lvl':>5} {'Count':>7}")
print("-" * 25)
for grade in range(5, 12):
    for lvl in range(1, 6):
        allowed = allowed_difficulty(lvl, SOURCE)
        cur.execute(
            'SELECT COUNT(*) FROM adaptive_tasks '
            'WHERE class_level = ? AND difficulty_level IN ({})'.format(
                ','.join('?' * len(allowed))),
            [grade] + allowed
        )
        cnt = cur.fetchone()[0]
        flag = " <<< EMPTY" if cnt == 0 else ""
        print(f"  Grade {grade:>2} L{lvl}: {cnt:>5}{flag}")

# ---------------------------------------------------------------
# 5.3: G8 and G11 empty cells
# ---------------------------------------------------------------
print()
print("=" * 60)
print("5.3: Empty cells G8 and G11")
print("=" * 60)

for grade in [8, 11]:
    empties = []
    for lvl in range(1, 6):
        allowed = allowed_difficulty(lvl, SOURCE)
        cur.execute(
            'SELECT COUNT(*) FROM adaptive_tasks '
            'WHERE class_level = ? AND difficulty_level IN ({})'.format(
                ','.join('?' * len(allowed))),
            [grade] + allowed
        )
        cnt = cur.fetchone()[0]
        if cnt == 0:
            empties.append(f'L{lvl}')
    if empties:
        print(f"  G{grade}: EMPTY cells = {', '.join(empties)}")
    else:
        print(f"  G{grade}: ALL cells filled!")

# ---------------------------------------------------------------
# 5.4: App test client - daily set for G11 user
# ---------------------------------------------------------------
print()
print("=" * 60)
print("5.4: Daily set for G11 test user (app.test_client)")
print("=" * 60)

with flask_app.test_client() as client:
    # Get a G11 daily set page
    resp = client.get('/daily?grade=11')
    status = resp.status_code
    # Check if we get tasks in response
    txt = resp.get_data(as_text=True)
    has_tasks = 'task_text' in txt or 'task-text' in txt or 'задач' in txt.lower()
    print(f"  GET /daily?grade=11 -> HTTP {status}")
    print(f"  Response has task content: {has_tasks}")
    # Try to get JSON
    resp2 = client.get('/api/tasks/daily?grade=11')
    print(f"  GET /api/tasks/daily?grade=11 -> HTTP {resp2.status_code}")

# ---------------------------------------------------------------
# 5.5: Re-run migration (idempotency)
# ---------------------------------------------------------------
print()
print("=" * 60)
print("5.5: Re-run migration (idempotency check)")
print("=" * 60)

import subprocess
result = subprocess.run(
    ['python', 'scripts/migrate_8to5_scale.py'],
    capture_output=True, text=True, cwd=BASE,
    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
)
# Check key lines
output = result.stdout
if 'already exists (idempotent)' in output:
    print("  [OK] Column already exists - idempotent")
if 'all already saved (idempotent)' in output:
    print("  [OK] Source values already saved - idempotent")
if 'No tasks outside 1..5 range' in output:
    print("  [OK] Still no tasks outside 1..5")

# Verify counts unchanged
cur.execute(
    'SELECT difficulty_level, COUNT(*) FROM adaptive_tasks '
    'GROUP BY difficulty_level ORDER BY difficulty_level'
)
dist = cur.fetchall()
total = sum(r[1] for r in dist)
print(f"  Total tasks: {total}")
for lvl, cnt in dist:
    print(f"  Level {lvl}: {cnt:>6}")

db.close()

# ---------------------------------------------------------------
# 5.6: Pytest
# ---------------------------------------------------------------
print()
print("=" * 60)
print("5.6: pytest -q")
print("=" * 60)

result = subprocess.run(
    ['python', '-m', 'pytest', '-q', '--tb=no'],
    capture_output=True, text=True, cwd=BASE, timeout=120,
    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
)
# Get last line with pass/fail count
lines = result.stdout.strip().split('\n')
for line in lines[-5:]:
    print(f"  {line}")
if result.stderr:
    for line in result.stderr.strip().split('\n')[-3:]:
        print(f"  [stderr] {line}")

print()
print("=" * 60)
print("DONE")
print("=" * 60)
