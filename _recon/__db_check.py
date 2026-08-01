"""Check all DB files in project - Task 1."""
import sqlite3
import os

# All .db files in project (non-empty)
db_files = []
base = r"c:\Users\Redmi\Desktop\Новая папка (2)"
for root, dirs, files in os.walk(base):
    # Skip .git, __pycache__, etc.
    if '.git' in root or '__pycache__' in root or 'node_modules' in root:
        continue
    for f in files:
        if f.endswith('.db'):
            fp = os.path.join(root, f)
            size = os.path.getsize(fp)
            mtime = os.path.getmtime(fp)
            if size > 0:
                db_files.append((fp, size, mtime))

print("=== NON-EMPTY DB FILES ===")
for fp, size, mtime in sorted(db_files):
    import datetime
    dt = datetime.datetime.fromtimestamp(mtime)
    print(f"  {fp}")
    print(f"    Size: {size} bytes, Modified: {dt.isoformat()}")

# Now check the two main candidates: formyla.db and instance/formyla.db
candidates = [
    os.path.join(base, 'formyla.db'),
    os.path.join(base, 'instance', 'formyla.db'),
]

print("\n=== MAIN DB CANDIDATES ===")
for db_path in candidates:
    print(f"\n--- {db_path} ---")
    print(f"  Exists: {os.path.exists(db_path)}, Size: {os.path.getsize(db_path) if os.path.exists(db_path) else 'N/A'}")
    if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        continue
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # List tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    print(f"  Tables ({len(tables)}): {tables}")
    
    # Check AdaptiveTask table for difficulty_level
    if 'adaptive_task' in tables:
        cur.execute("SELECT MAX(difficulty_level) FROM adaptive_task")
        max_dl = cur.fetchone()[0]
        print(f"  Max difficulty_level: {max_dl}")
        
        cur.execute("PRAGMA table_info(adaptive_task)")
        cols = [r[1] for r in cur.fetchall()]
        has_dl_src = 'difficulty_level_src' in cols
        print(f"  Has difficulty_level_src: {has_dl_src}")
        print(f"  AdaptiveTask columns: {cols}")
        
        cur.execute("SELECT COUNT(*) FROM adaptive_task")
        n_tasks = cur.fetchone()[0]
        print(f"  Number of tasks: {n_tasks}")
    
    # Check task_assignment_history
    has_tah = 'task_assignment_history' in tables
    print(f"  Has task_assignment_history: {has_tah}")
    
    if has_tah:
        cur.execute("SELECT COUNT(*) FROM task_assignment_history")
        n_assign = cur.fetchone()[0]
        print(f"  task_assignment_history rows: {n_assign}")
    
    # Check if there's an adaptive_test_result table
    if 'adaptive_test_result' in tables:
        cur.execute("PRAGMA table_info(adaptive_test_result)")
        atr_cols = [r[1] for r in cur.fetchall()]
        has_task_ids = 'task_ids' in atr_cols
        print(f"  adaptive_test_result columns: {atr_cols}")
        print(f"  Has task_ids column: {has_task_ids}")
        
        cur.execute("SELECT COUNT(*) FROM adaptive_test_result")
        n_atr = cur.fetchone()[0]
        print(f"  adaptive_test_result rows: {n_atr}")
    
    conn.close()

# Now check what app.py actually computes as the database URL
print("\n=== RUNTIME DB URL (from app.py logic) ===")
os.environ.pop('DATABASE_URL', None)
os.environ.pop('RENDER', None)
_database_url = os.environ.get('DATABASE_URL', 'sqlite:///formyla.db')
print(f"  DATABASE_URL env: {os.environ.get('DATABASE_URL', 'NOT SET')}")
print(f"  Computed _database_url: {_database_url}")
print(f"  Resolves to: sqlite:///{os.path.join(os.getcwd(), 'formyla.db') if _database_url.startswith('sqlite:///') else _database_url}")
print(f"  CWD: {os.getcwd()}")
