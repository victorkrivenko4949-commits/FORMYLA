# -*- coding: utf-8 -*-
"""TASK 2: Referential integrity check on instance DB and root DB."""
import sqlite3
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DB = os.path.join(BASE, 'formyla.db')
INSTANCE_DB = os.path.join(BASE, 'instance', 'formyla.db')

print("="*80)
print("TASK 2: REFERENTIAL INTEGRITY CHECK")
print("="*80)

# ── Part A: Find all columns named task_id in instance DB ──
conn = sqlite3.connect(INSTANCE_DB)
cur = conn.cursor()

# Get all tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]

print("\n--- Part A: All task_id columns in instance DB ---")
task_id_tables = []
for tbl in tables:
    cur.execute(f'PRAGMA table_info("{tbl}")')
    cols = [c[1] for c in cur.fetchall()]
    if 'task_id' in cols:
        cur.execute(f'SELECT task_id FROM "{tbl}" WHERE task_id IS NOT NULL')
        ids = [r[0] for r in cur.fetchall()]
        task_id_tables.append((tbl, ids))
        unique_ids = sorted(set(ids))
        print(f"\n  {tbl}: {len(ids)} rows with task_id")
        print(f"    Unique task_ids: {unique_ids[:30]}{'...' if len(unique_ids) > 30 else ''}")
        if ids:
            print(f"    Min={min(ids)}, Max={max(ids)}")

# ── Part B: Search for any other FK columns referencing tasks ──
print("\n--- Part B: Other columns that may reference tasks ---")
for tbl in tables:
    cur.execute(f'PRAGMA table_info("{tbl}")')
    cols_info = cur.fetchall()
    for ci in cols_info:
        col_name = ci[1]
        if 'task' in col_name.lower() and col_name != 'task_id':
            cur.execute(f'SELECT DISTINCT {col_name} FROM "{tbl}" WHERE {col_name} IS NOT NULL LIMIT 20')
            vals = [r[0] for r in cur.fetchall()]
            print(f"  {tbl}.{col_name}: {vals}")

conn.close()

# ── Part C: What IDs are in root adaptive_tasks? ──
conn = sqlite3.connect(ROOT_DB)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
total = cur.fetchone()[0]
cur.execute("SELECT MIN(id), MAX(id) FROM adaptive_tasks")
min_id, max_id = cur.fetchone()
print(f"\n--- Part C: root adaptive_tasks ID range ---")
print(f"  Total rows: {total}")
print(f"  id range: {min_id} .. {max_id}")

# Check gaps
cur.execute("SELECT id FROM adaptive_tasks ORDER BY id")
ids_list = [r[0] for r in cur.fetchall()]
expected = set(range(min_id, max_id + 1))
actual = set(ids_list)
missing = sorted(expected - actual)
extra = sorted(actual - expected)
if missing:
    print(f"  Missing IDs ({len(missing)}): {missing[:20]}{'...' if len(missing) > 20 else ''}")
else:
    print("  No missing IDs - contiguous sequence")
if extra:
    print(f"  IDs outside range ({len(extra)}): {extra[:20]}")

# ── Part D: Key columns info ──
cur.execute("PRAGMA table_info(adaptive_tasks)")
cols = cur.fetchall()
print("\n--- Part D: adaptive_tasks schema in root ---")
for c in cols:
    print(f"  {c[1]:30s} {c[2]:10s} nullable={c[3]} default={c[4]} pk={c[5]}")

# Check difficulty_level range
cur.execute("SELECT DISTINCT difficulty_level FROM adaptive_tasks ORDER BY 1")
levels = [r[0] for r in cur.fetchall()]
print(f"\n  difficulty_level distinct values: {levels}")

cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE difficulty_level IS NULL")
null_levels = cur.fetchone()[0]
print(f"  NULL difficulty_level: {null_levels}")

cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE difficulty_level IS NOT NULL AND (difficulty_level < 1 OR difficulty_level > 5)")
out_of_range = cur.fetchone()[0]
print(f"  Out of 1..5 range: {out_of_range}")

# Check difficulty_level_src
cur.execute("SELECT DISTINCT difficulty_level_src FROM adaptive_tasks")
src_vals = [r[0] for r in cur.fetchall()]
print(f"  difficulty_level_src values: {src_vals}")

# ── Part E: Check if instance has overlapping IDs ──
conn2 = sqlite3.connect(INSTANCE_DB)
cur2 = conn2.cursor()

# Check all tables in instance that HAVE an adaptive_tasks table
cur2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='adaptive_tasks'")
has_adaptive = cur2.fetchone() is not None
if has_adaptive:
    cur2.execute("SELECT COUNT(*), MIN(id), MAX(id) FROM adaptive_tasks")
    a_cnt, a_min, a_max = cur2.fetchone()
    print(f"\n--- Part E: instance adaptive_tasks ---")
    print(f"  Rows: {a_cnt}, id range: {a_min}..{a_max}")
else:
    print(f"\n--- Part E: instance has NO adaptive_tasks table ---")

conn2.close()
conn.close()

print("\nDone.")
