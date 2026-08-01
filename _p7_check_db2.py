import sqlite3, os
db_path = 'instance/formyla.db'
if os.path.exists(db_path):
    sz = os.path.getsize(db_path)
    c = sqlite3.connect(db_path)
    tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print(f"{db_path}: {sz} bytes")
    print(f"Tables: {[t[0] for t in tables]}")
    if 'adaptive_tasks' in [t[0] for t in tables]:
        cnt = c.execute("SELECT COUNT(*) FROM adaptive_tasks").fetchone()[0]
        print(f"adaptive_tasks rows: {cnt}")
        # check class_level distribution
        grades = c.execute("SELECT DISTINCT class_level FROM adaptive_tasks").fetchall()
        print(f"Grades: {[g[0] for g in grades]}")
    else:
        print("adaptive_tasks table NOT FOUND in instance/formyla.db")
    c.close()
else:
    print(f"{db_path}: NOT FOUND")
