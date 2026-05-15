"""Backup adaptive_tasks to JSON, then truncate the table.

Creates a timestamped JSON dump in adaptive_data/_backups/ before deletion
so we can always roll back if regeneration goes wrong.
"""

from __future__ import annotations
import sqlite3
import json
import os
import sys
import datetime as _dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "instance", "formyla.db")
BACKUP_DIR = os.path.join(ROOT, "adaptive_data", "_backups")


def main():
    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        sys.exit(1)

    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"adaptive_tasks_{ts}.json")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    total = cur.fetchone()[0]
    print(f"Tasks before wipe: {total}")

    if total > 0:
        cur.execute("SELECT * FROM adaptive_tasks")
        rows = [dict(r) for r in cur.fetchall()]
        with open(backup_path, "w", encoding="utf-8") as fp:
            json.dump(rows, fp, ensure_ascii=False, indent=2)
        print(f"Backup saved: {backup_path}  ({len(rows)} rows)")
    else:
        print("Table empty — no backup needed")

    print("Truncating adaptive_tasks…")
    cur.execute("DELETE FROM adaptive_tasks")
    # Reset autoincrement
    try:
        cur.execute("DELETE FROM sqlite_sequence WHERE name='adaptive_tasks'")
    except Exception:
        pass
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    after = cur.fetchone()[0]
    print(f"Tasks after wipe: {after}")
    conn.close()


if __name__ == "__main__":
    main()
