"""Pre-check schemas & row counts before migration."""
import sqlite3, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(BASE, 'formyla.db')
INST = os.path.join(BASE, 'instance', 'formyla.db')

def schema(db, table):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info('{table}')")
    cols = cur.fetchall()
    conn.close()
    return cols

def row_count(db, table):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    n = cur.fetchone()[0]
    conn.close()
    return n

print("=== instance adaptive_tasks schema ===")
for c in schema(INST, 'adaptive_tasks'):
    print(f"  {c[1]:35s} {c[2]:12s} nullable={c[3]} default={c[4]}")

print(f"\n  Rows: {row_count(INST, 'adaptive_tasks')}")

print("\n=== root adaptive_tasks schema ===")
for c in schema(ROOT, 'adaptive_tasks'):
    print(f"  {c[1]:35s} {c[2]:12s} nullable={c[3]} default={c[4]}")

print(f"\n  Rows: {row_count(ROOT, 'adaptive_tasks')}")

print("\n=== instance task_assignment_history schema ===")
for c in schema(INST, 'task_assignment_history'):
    print(f"  {c[1]:35s} {c[2]:12s} nullable={c[3]} default={c[4]}")
print(f"  Rows: {row_count(INST, 'task_assignment_history')}")

print("\n=== root task_assignment_history schema ===")
for c in schema(ROOT, 'task_assignment_history'):
    print(f"  {c[1]:35s} {c[2]:12s} nullable={c[3]} default={c[4]}")
print(f"  Rows: {row_count(ROOT, 'task_assignment_history')}")

# Check: which columns in root are NOT in instance?
root_cols = {c[1] for c in schema(ROOT, 'adaptive_tasks')}
inst_cols = {c[1] for c in schema(INST, 'adaptive_tasks')}
only_root = root_cols - inst_cols
only_inst = inst_cols - root_cols
print(f"\n=== adaptive_tasks column diff ===")
print(f"  In root only: {only_root}")
print(f"  In instance only: {only_inst}")

# task_assignment_history diff
root_cols_h = {c[1] for c in schema(ROOT, 'task_assignment_history')}
inst_cols_h = {c[1] for c in schema(INST, 'task_assignment_history')}
print(f"\n=== task_assignment_history column diff ===")
print(f"  In root only: {root_cols_h - inst_cols_h}")
print(f"  In instance only: {inst_cols_h - root_cols_h}")
