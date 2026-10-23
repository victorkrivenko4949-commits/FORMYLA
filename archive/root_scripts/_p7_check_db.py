import sqlite3, os
dbs = ['database.db', 'instance/formyla.db', 'formyla.db']
for db in dbs:
    if os.path.exists(db):
        sz = os.path.getsize(db)
        c = sqlite3.connect(db)
        cnt = c.execute("SELECT COUNT(*) FROM adaptive_tasks").fetchone()[0]
        print(f"{db}: {sz} bytes, AdaptiveTask rows={cnt}")
        c.close()
    else:
        print(f"{db}: NOT FOUND")
