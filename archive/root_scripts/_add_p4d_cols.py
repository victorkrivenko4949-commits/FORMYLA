"""Add missing P4D/P9 columns to local SQLite DB."""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), 'instance', 'formyla.db')
conn = sqlite3.connect(DB)
cols = [c[1] for c in conn.execute("PRAGMA table_info(daily_task_items)").fetchall()]

migrations = [
    ("debt_status", "TEXT DEFAULT NULL"),
    ("debt_until", "DATE DEFAULT NULL"),
    ("is_calibration", "BOOLEAN NOT NULL DEFAULT 0"),
]

for col_name, col_def in migrations:
    if col_name not in cols:
        print(f"Adding column: {col_name} {col_def}")
        conn.execute(f"ALTER TABLE daily_task_items ADD COLUMN {col_name} {col_def}")
        conn.commit()
    else:
        print(f"Column already exists: {col_name}")

# Verify
cols2 = [c[1] for c in conn.execute("PRAGMA table_info(daily_task_items)").fetchall()]
print(f"\nFinal columns ({len(cols2)}): {cols2}")
conn.close()
print("Done.")
