"""Check adaptive_tasks columns and difficulty_level in both DBs."""
import sqlite3
import os

base = r"c:\Users\Redmi\Desktop\Новая папка (2)"
dbs = [
    os.path.join(base, 'formyla.db'),
    os.path.join(base, 'instance', 'formyla.db'),
]

for db_path in dbs:
    print(f"\n{'='*60}")
    print(f"DB: {db_path}")
    print(f"Size: {os.path.getsize(db_path)}, Modified: {os.path.getmtime(db_path)}")
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # adaptive_tasks (plural)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='adaptive_tasks'")
    if cur.fetchone():
        cur.execute("PRAGMA table_info(adaptive_tasks)")
        cols = [(r[1], r[2]) for r in cur.fetchall()]
        print(f"  adaptive_tasks columns: {cols}")
        
        cur.execute("SELECT MAX(difficulty_level) FROM adaptive_tasks")
        max_dl = cur.fetchone()[0]
        print(f"  MAX difficulty_level: {max_dl}")
        
        has_dl_src = any(c[0] == 'difficulty_level_src' for c in cols)
        print(f"  Has difficulty_level_src: {has_dl_src}")
        
        cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
        n = cur.fetchone()[0]
        print(f"  Number of tasks: {n}")
    else:
        print("  adaptive_tasks: NOT FOUND")
    
    # task_assignment_history
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_assignment_history'")
    if cur.fetchone():
        cur.execute("SELECT COUNT(*) FROM task_assignment_history")
        n = cur.fetchone()[0]
        print(f"  task_assignment_history rows: {n}")
    
    # adaptive_test_results (for task_ids column)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='adaptive_test_results'")
    if cur.fetchone():
        cur.execute("PRAGMA table_info(adaptive_test_results)")
        cols = [r[1] for r in cur.fetchall()]
        print(f"  adaptive_test_results columns: {cols}")
        has_task_ids = 'task_ids' in cols
        print(f"  Has task_ids: {has_task_ids}")
    else:
        print("  adaptive_test_results: NOT FOUND")
    
    # models.py - check if model has task_ids
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='adaptive_test_result'")
    if cur.fetchone():
        cur.execute("PRAGMA table_info(adaptive_test_result)")
        cols = [r[1] for r in cur.fetchall()]
        print(f"  adaptive_test_result (singular) columns: {cols}")
    
    conn.close()

print("\n\n=== WHICH DB DOES APP.PY USE? ===")
print("app.py line 178: _database_url = os.environ.get('DATABASE_URL', 'sqlite:///formyla.db')")
print("No DATABASE_URL env → defaults to sqlite:///formyla.db")
print("This resolves to formyla.db in CWD (project root)")

# Compare sizes of both
s1 = os.path.getsize(os.path.join(base, 'formyla.db'))
s2 = os.path.getsize(os.path.join(base, 'instance', 'formyla.db'))
print(f"\nRoot formyla.db: {s1} bytes")
print(f"Instance/formyla.db: {s2} bytes")
print(f"Same size: {s1 == s2}")

import hashlib
h1 = hashlib.md5(open(os.path.join(base, 'formyla.db'), 'rb').read()).hexdigest()
h2 = hashlib.md5(open(os.path.join(base, 'instance', 'formyla.db'), 'rb').read()).hexdigest()
print(f"Root MD5: {h1}")
print(f"Instance MD5: {h2}")
print(f"Identical: {h1 == h2}")
