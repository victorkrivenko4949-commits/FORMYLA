#!/usr/bin/env python
"""Diagnose DB state - output to file."""
import sqlite3, sys, os

db_path = r"../../Downloads/FORMYLA_CONDITION_COURT/runs/selection_675_night_20260713/condition_court_state.sqlite"
out_path = os.path.join(os.path.dirname(__file__), "_db_state.txt")

lines = []
db = sqlite3.connect(db_path)

# Tables
cur = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
lines.append("=== TABLES ===")
for r in cur.fetchall():
    lines.append(f"  {r[0]}")

# Stage status
cur = db.execute('SELECT status, COUNT(*) as cnt FROM task_stage_status GROUP BY status ORDER BY cnt DESC')
lines.append("\n=== STAGE STATUS ===")
for r in cur.fetchall():
    lines.append(f"  {r[0]}: {r[1]}")

cur = db.execute('SELECT COUNT(DISTINCT task_id) FROM task_stage_status')
lines.append(f"\nUnique tasks: {cur.fetchone()[0]}")

# agent_calls
cur = db.execute('SELECT COUNT(*) FROM agent_calls')
lines.append(f"Total agent_calls: {cur.fetchone()[0]}")

try:
    cur = db.execute('SELECT COUNT(*) FROM task_results')
    lines.append(f"Total task_results: {cur.fetchone()[0]}")
    cur = db.execute('SELECT decision, COUNT(*) as cnt FROM task_results GROUP BY decision ORDER BY cnt DESC')
    lines.append("\n=== DECISIONS ===")
    for r in cur.fetchall():
        lines.append(f"  {r[0]}: {r[1]}")
except Exception as e:
    lines.append(f"\nNo task_results table: {e}")

# Failed tasks
cur = db.execute("SELECT DISTINCT task_id FROM task_stage_status WHERE status='failed'")
failed_tasks = [r[0] for r in cur.fetchall()]
lines.append(f"\n=== FAILED TASKS ({len(failed_tasks)}) ===")
for t in failed_tasks[:30]:
    lines.append(f"  {t}")

# Pending tasks (tasks where ALL stage-1 agents are pending)
cur = db.execute("""
    SELECT DISTINCT s.task_id FROM task_stage_status s 
    WHERE s.status='pending' 
    AND s.agent_role IN ('condition_lawyer','math_skeptic','level_calibrator_a','level_calibrator_b','taxonomy_auditor','duplicate_hunter')
    GROUP BY s.task_id
    HAVING COUNT(*) >= 6
    ORDER BY s.task_id
    LIMIT 10
""")
pending_tasks = [r[0] for r in cur.fetchall()]
lines.append(f"\n=== FULLY PENDING TASKS (first 10) ===")
for t in pending_tasks:
    lines.append(f"  {t}")

# Agents distribution
cur = db.execute("SELECT agent_role, status, COUNT(*) FROM task_stage_status GROUP BY agent_role, status ORDER BY agent_role, status")
lines.append("\n=== AGENT STATUS BREAKDOWN ===")
for r in cur.fetchall():
    lines.append(f"  {r[0]}: {r[1]}={r[2]}")

# Runs
cur = db.execute('SELECT run_id, started_at_utc, updated_at_utc, status FROM runs ORDER BY started_at_utc')
lines.append("\n=== RUNS ===")
for r in cur.fetchall():
    lines.append(f"  run_id={r[0]}, started={r[1]}, updated={r[2]}, status={r[3]}")

db.close()

with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print(f"Output written to {out_path}")
