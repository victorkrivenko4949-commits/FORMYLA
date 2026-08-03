# -*- coding: utf-8 -*-
"""Temporary helper script for D9_FIX diagnostics. Remove after use."""
import os, sys

# --- Formula calculation ---
print("=== FORMULA 5 STEPS ===")
mu, sigma = 3.0, 1.5
for step in range(1, 6):
    sigma = max(0.35, sigma * 0.94)
    mu = mu + 0.22 * (sigma + 0.3)
    print("step=%d mu=%.3f sigma=%.3f" % (step, mu, sigma))
print("FINAL_MU: %.3f" % mu)

# --- Search mu/sigma in code files ---
print("\n=== MU/SIGMA ASSIGNMENTS ===")
files = ['services/theme_probe.py', 'services/level_engine.py', 'routes/prep.py']
for fpath in files:
    if not os.path.exists(fpath):
        continue
    print("\n--- %s ---" % fpath)
    for i, line in enumerate(open(fpath, encoding='utf-8').readlines(), 1):
        ll = line.lower()
        if ('mu' in ll or 'sigma' in ll) and ('=' in line or 'clamp' in ll or 'min(' in line or 'max(' in line or 'round' in line or 'default' in ll):
            print("%d: %s" % (i, line.rstrip()))

# --- SolutionAttempt creation points ---
print("\n=== SolutionAttempt CREATION ===")
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__', 'venv', '.venv')]
    for fn in files:
        if fn.endswith('.py'):
            try:
                for i, line in enumerate(open(os.path.join(root, fn), encoding='utf-8', errors='ignore').readlines(), 1):
                    if 'SolutionAttempt(' in line:
                        print("%s:%d: %s" % (os.path.join(root, fn), i, line.rstrip()))
            except Exception:
                pass

# --- record_answer calls ---
print("\n=== record_answer CALLS ===")
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__', 'venv', '.venv')]
    for fn in files:
        if fn.endswith('.py'):
            try:
                for i, line in enumerate(open(os.path.join(root, fn), encoding='utf-8', errors='ignore').readlines(), 1):
                    if 'record_answer' in line:
                        print("%s:%d: %s" % (os.path.join(root, fn), i, line.rstrip()))
            except Exception:
                pass

# --- adaptive_tasks state ---
print("\n=== ADAPTIVE_TASKS STATE ===")
import sqlite3
c = sqlite3.connect('instance/formyla.db')
total = c.execute('SELECT COUNT(*) FROM adaptive_tasks').fetchone()
print("TOTAL", total)
for r in c.execute('SELECT difficulty_level, COUNT(*) FROM adaptive_tasks GROUP BY difficulty_level ORDER BY difficulty_level'):
    print(r)

# --- Check probe_id in solution_attempts ---
print("\n=== SOLUTION_ATTEMPTS ===")
c.row_factory = sqlite3.Row
rows = c.execute('SELECT * FROM solution_attempts ORDER BY id DESC LIMIT 10').fetchall()
print("COUNT:", len(rows))
for r in rows:
    d = dict(r)
    print("id=%s probe_id=%s" % (d.get('id'), d.get('probe_id')))

c.close()

# --- File lengths ---
print("\n=== FILE LENGTHS ===")
for fpath in ['services/theme_probe.py', 'routes/prep.py', 'models.py']:
    n = len(open(fpath, encoding='utf-8').readlines())
    print("%s: %d lines" % (fpath, n))
