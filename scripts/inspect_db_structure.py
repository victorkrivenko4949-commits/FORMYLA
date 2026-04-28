"""Inspect database structure for LaTeX cleanup task."""
import sqlite3

con = sqlite3.connect('instance/formyla.db')

# List all tables
tables = [r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()]
print("TABLES:", tables)

# Show columns for each table
for t in tables:
    cols = con.execute(f'PRAGMA table_info({t})').fetchall()
    col_names = [(r[1], r[2]) for r in cols]
    print(f"\n--- {t} ---")
    print(col_names)

# Check for adaptive-related tables
for t in tables:
    if 'task' in t.lower() or 'problem' in t.lower() or 'adaptive' in t.lower():
        count = con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        print(f"\n>>> {t}: {count} rows")
        # Show first row
        row = con.execute(f'SELECT * FROM {t} LIMIT 1').fetchone()
        if row:
            cols = [r[1] for r in con.execute(f'PRAGMA table_info({t})').fetchall()]
            for c, v in zip(cols, row):
                val_str = str(v)[:150] if v else 'NULL'
                print(f"  {c}: {val_str}")

con.close()
