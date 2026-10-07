import sqlite3, os
dbs = ['instance/formyla.db', 'instance/database.db', 'database.db', 'formyla.db']
for d in dbs:
    try:
        sz = os.path.getsize(d)
        db = sqlite3.connect(d)
        cols = [c[1] for c in db.execute('PRAGMA table_info(daily_task_items)').fetchall()]
        print(f'{d}: {sz} bytes')
        print(f'  columns({len(cols)}): {cols[:8]}...')
        print(f'  debt_status={"debt_status" in cols} is_calibration={"is_calibration" in cols}')
        db.close()
    except Exception as e:
        print(f'{d}: ERROR {e}')
