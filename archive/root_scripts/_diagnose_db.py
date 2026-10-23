#!/usr/bin/env python
"""Diagnose current DB state for 675 run."""
import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else r"../../Downloads/FORMYLA_CONDITION_COURT/runs/selection_675_night_20260713/condition_court_state.sqlite"

db = sqlite3.connect(db_path)

# Check task_stage_status
cur = db.execute('SELECT status, COUNT(*) as cnt FROM task_stage_status GROUP BY status ORDER BY cnt DESC')
rows = cur.fetchall()
print('=== STAGE STATUS DISTRIBUTION ===')
for r in rows:
    print(f'  {r[0]}: {r[1]}')

# Unique tasks
cur2 = db.execute('SELECT COUNT(DISTINCT task_id) FROM task_stage_status')
print(f'\nUnique tasks in stage_status: {cur2.fetchone()[0]}')

# agent_calls
cur3 = db.execute('SELECT COUNT(*) FROM agent_calls')
print(f'Total agent_calls: {cur3.fetchone()[0]}')

# task_results
cur4 = db.execute('SELECT COUNT(*) FROM task_results')
print(f'Total task_results: {cur4.fetchone()[0]}')

# Decisions
cur5 = db.execute('SELECT decision, COUNT(*) as cnt FROM task_results GROUP BY decision ORDER BY cnt DESC')
rows5 = cur5.fetchall()
print('\n=== DECISIONS ===')
for r in rows5:
    print(f'  {r[0]}: {r[1]}')

# Runs
cur6 = db.execute('SELECT run_id, started_at_utc, updated_at_utc, status FROM runs')
rows6 = cur6.fetchall()
print('\n=== RUNS ===')
for r in rows6:
    print(f'  run_id={r[0][:20]}..., started={r[1]}, updated={r[2]}, status={r[3]}')

# Failed tasks with task_id
cur7 = db.execute('''
    SELECT DISTINCT t.task_id, t.status 
    FROM task_stage_status t 
    WHERE t.status='failed'
    ORDER BY t.task_id
    LIMIT 30
''')
rows7 = cur7.fetchall()
print('\n=== FAILED TASKS (first 30) ===')
for r in rows7:
    print(f'  task_id={r[0]}, status={r[1]}')

# Tasks with no result
cur8 = db.execute('''
    SELECT DISTINCT s.task_id 
    FROM task_stage_status s 
    WHERE s.task_id NOT IN (SELECT task_id FROM task_results)
    ORDER BY s.task_id
    LIMIT 20
''')
rows8 = cur8.fetchall()
print('\n=== TASKS WITH NO RESULT (first 20) ===')
for r in rows8:
    print(f'  task_id={r[0]}')

db.close()
print('\nDone.')
