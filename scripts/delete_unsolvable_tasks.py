"""Delete tasks whose answer/solution clearly indicates the task is unsolvable.

Backs up deleted rows to adaptive_data/_backups/deleted_unsolvable_<ts>.json.

NOTE: SQLite's LOWER() does NOT lowercase Cyrillic, so we filter in Python.
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

ANSWER_BAD = [
    "нет решений", "не существует", "невозможно",
    "нельзя", "не имеет реш", "задача не имеет",
    "нет такого", "нет ответа", "невыполнимо",
]
SOLUTION_BAD = [
    "задача не имеет решений",
    "уточните, пожалуйста",
    "не существует точки",
    "не существует такого",
    "нет решения у задачи",
    "противоречие в условии",
    "условие задачи некорректно",
    "задача поставлена некорректно",
    "задача не имеет решения",
    "решений не существует",
]
ANSWER_BAD = [p.lower() for p in ANSWER_BAD]
SOLUTION_BAD = [p.lower() for p in SOLUTION_BAD]

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT * FROM adaptive_tasks")
all_rows = cur.fetchall()

bad = []
for r in all_rows:
    ans = (r["correct_answer"] or "").lower()
    sol = (r["solution"] or "").lower()
    matched = None
    for p in ANSWER_BAD:
        if p in ans:
            matched = ("answer", p)
            break
    if not matched:
        for p in SOLUTION_BAD:
            if p in sol:
                matched = ("solution", p)
                break
    if matched:
        bad.append((dict(r), matched))

print(f"Tasks matching unsolvable criteria: {len(bad)}")

if not bad:
    print("Nothing to delete.")
else:
    for row, (where_, pat) in bad[:30]:
        snippet = (row["task_text"] or "")[:120].replace("\n", " ")
        print(f"  id={row['id']} cl={row['class_level']} L={row['difficulty_level']} "
              f"[{where_}={pat!r}] {snippet}...")
    if len(bad) > 30:
        print(f"  ... +{len(bad) - 30} more")

    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"deleted_unsolvable_{ts}.json")
    with open(backup_path, "w", encoding="utf-8") as fp:
        json.dump([row for row, _m in bad], fp, ensure_ascii=False, indent=2)
    print(f"Backup: {backup_path}")

    ids = [row["id"] for row, _m in bad]
    placeholders = ",".join("?" * len(ids))
    cur.execute(f"DELETE FROM adaptive_tasks WHERE id IN ({placeholders})", ids)
    conn.commit()
    print(f"Deleted: {cur.rowcount}")

cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
print(f"Remaining tasks: {cur.fetchone()[0]}")
conn.close()
