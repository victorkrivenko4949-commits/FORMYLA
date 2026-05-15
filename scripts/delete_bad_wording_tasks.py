"""Delete adaptive tasks whose TASK_TEXT contains forbidden wording.

NOTE: SQLite's LOWER() does NOT lowercase Cyrillic by default — it only
handles ASCII. So we fetch all rows and filter in Python with proper
case-insensitive matching.

Backs up deleted rows to adaptive_data/_backups/deleted_bad_wording_<ts>.json.
"""
import sqlite3
import json
import os
import sys
import datetime as _dt

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "instance", "formyla.db")
BACKUP_DIR = os.path.join(ROOT, "adaptive_data", "_backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

# Forbidden wording (case-insensitive substring match)
TEXT_BAD = [
    "сколько решений имеет",
    "сколько решений у задач",
    "сколько решений может",
    "сколько различных решений",
    "сколько различных значений",
    "сколько различных пар",
    "число решений задачи",
    "число решений уравнения",
    "число решений неравенства",
    "количество решений задачи",
    "количество решений уравнения",
    "количество различных решений",
    "имеет задача",
    "имеет ли задача решен",
    "сколько вариантов имеет",
    "найдите количество решений",
    "найдите число решений",
    "сколько корней имеет",
    "число корней уравнения",
    "количество корней уравнения",
]

TEXT_BAD_LOWER = [p.lower() for p in TEXT_BAD]

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT * FROM adaptive_tasks")
all_rows = cur.fetchall()

bad = []
for r in all_rows:
    txt = (r["task_text"] or "").lower()
    for pat in TEXT_BAD_LOWER:
        if pat in txt:
            bad.append((dict(r), pat))
            break

print(f"Tasks with forbidden wording in task_text: {len(bad)}")
for row, pat in bad:
    snippet = (row["task_text"] or "")[:160].replace("\n", " ")
    print(
        f"  id={row['id']} cl={row['class_level']} L={row['difficulty_level']} "
        f"topic={row['topic']!r} pat={pat!r}\n    {snippet}..."
    )

if bad:
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"deleted_bad_wording_{ts}.json")
    with open(backup_path, "w", encoding="utf-8") as fp:
        json.dump([row for row, _p in bad], fp, ensure_ascii=False, indent=2)
    print(f"\nBackup saved: {backup_path}")

    ids = [row["id"] for row, _p in bad]
    placeholders = ",".join("?" * len(ids))
    cur.execute(
        f"DELETE FROM adaptive_tasks WHERE id IN ({placeholders})", ids
    )
    conn.commit()
    print(f"Deleted: {cur.rowcount}")

cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
print(f"Remaining tasks: {cur.fetchone()[0]}")
conn.close()
