"""Check all DB files in _recon for task counts."""
import sqlite3
import os
import datetime

BASE = r"c:\Users\Redmi\Desktop\Новая папка (2)"
recon = os.path.join(BASE, "_recon")
dbs = [f for f in os.listdir(recon) if f.endswith('.db') and not f.endswith('-shm') and not f.endswith('-wal')]

for f in sorted(dbs):
    path = os.path.join(recon, f)
    size = os.path.getsize(path)
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path))
    print(f"\n=== {f} ===")
    print(f"  size={size}  mtime={mtime}")
    try:
        conn = sqlite3.connect(path)
        c = conn.cursor()
        tables = [t[0] for t in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        
        if 'adaptive_tasks' in tables:
            c.execute('SELECT COUNT(*) FROM adaptive_tasks')
            at = c.fetchone()[0]
            print(f"  adaptive_tasks={at}")
            
            # Check grade/level breakdown
            try:
                c.execute("PRAGMA table_info(adaptive_tasks)")
                cols = [r[1] for r in c.fetchall()]
                has_grade = 'grade' in cols or 'class_id' in cols
                has_level = 'difficulty_level' in cols or 'level' in cols
                
                if has_grade and has_level:
                    grade_col = 'grade' if 'grade' in cols else 'class_id'
                    level_col = 'difficulty_level' if 'difficulty_level' in cols else 'level'
                    c.execute(f"SELECT {grade_col}, {level_col}, COUNT(*) FROM adaptive_tasks GROUP BY {grade_col}, {level_col} ORDER BY {grade_col}, {level_col}")
                    for r in c.fetchall():
                        print(f"    g={r[0]} l={r[1]}: {r[2]}")
            except Exception as e:
                print(f"  (breakdown error: {e})")
        else:
            print(f"  NO adaptive_tasks table")
            if at == 0:
                pass
        
        if 'users' in tables:
            c.execute('SELECT COUNT(*) FROM users')
            print(f"  users={c.fetchone()[0]}")
        
        if 'task_assignment_history' in tables:
            c.execute('SELECT COUNT(*) FROM task_assignment_history')
            print(f"  assignment_history={c.fetchone()[0]}")

        if 'task_solutions' in tables:
            c.execute('SELECT COUNT(*) FROM task_solutions')
            print(f"  task_solutions={c.fetchone()[0]}")

        conn.close()
    except Exception as e:
        print(f"  ERROR: {e}")

# Also check the root and instance DBs
for label, dbpath in [
    ("ROOT formyla.db", os.path.join(BASE, "formyla.db")),
    ("INSTANCE formyla.db", os.path.join(BASE, "instance", "formyla.db")),
]:
    print(f"\n=== {label} ===")
    size = os.path.getsize(dbpath)
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(dbpath))
    print(f"  size={size}  mtime={mtime}")
    try:
        conn = sqlite3.connect(dbpath)
        c = conn.cursor()
        tables = [t[0] for t in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        
        if 'adaptive_tasks' in tables:
            c.execute('SELECT COUNT(*) FROM adaptive_tasks')
            at = c.fetchone()[0]
            print(f"  adaptive_tasks={at}")
            
            try:
                c.execute("PRAGMA table_info(adaptive_tasks)")
                cols = [r[1] for r in c.fetchall()]
                has_grade = 'grade' in cols or 'class_id' in cols
                has_level = 'difficulty_level' in cols or 'level' in cols
                
                if has_grade and has_level:
                    grade_col = 'grade' if 'grade' in cols else 'class_id'
                    level_col = 'difficulty_level' if 'difficulty_level' in cols else 'level'
                    c.execute(f"SELECT {grade_col}, {level_col}, COUNT(*) FROM adaptive_tasks GROUP BY {grade_col}, {level_col} ORDER BY {grade_col}, {level_col}")
                    for r in c.fetchall():
                        print(f"    g={r[0]} l={r[1]}: {r[2]}")
            except Exception as e:
                print(f"  (breakdown error: {e})")
        else:
            print(f"  NO adaptive_tasks table")
        
        if 'users' in tables:
            c.execute('SELECT COUNT(*) FROM users')
            print(f"  users={c.fetchone()[0]}")
        
        if 'task_assignment_history' in tables:
            c.execute('SELECT COUNT(*) FROM task_assignment_history')
            print(f"  assignment_history={c.fetchone()[0]}")

        if 'task_solutions' in tables:
            c.execute('SELECT COUNT(*) FROM task_solutions')
            print(f"  task_solutions={c.fetchone()[0]}")

        if 'survey_responses' in tables:
            c.execute('SELECT COUNT(*) FROM survey_responses')
            print(f"  survey_responses={c.fetchone()[0]}")

        if 'debt_records' in tables:
            c.execute('SELECT COUNT(*) FROM debt_records')
            print(f"  debt_records={c.fetchone()[0]}")

        conn.close()
    except Exception as e:
        print(f"  ERROR: {e}")
