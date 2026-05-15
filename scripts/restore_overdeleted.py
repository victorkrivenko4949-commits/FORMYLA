"""Restore tasks that were overzealously deleted by the unsolvable filter.

We only want to KEEP-DELETED the tasks where the SOLUTION explicitly says
the task generation failed (e.g. "задача не имеет решения" because the
LLM gave up). We must RESTORE everything else: 'нельзя' answers etc are
perfectly legitimate olympiad tasks ('Можно ли... ?' → 'Нельзя, потому что …').
"""
import sqlite3
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "instance", "formyla.db")
BACKUP_DIR = os.path.join(ROOT, "adaptive_data", "_backups")

# Find latest deleted_unsolvable_* backup
files = sorted(
    [f for f in os.listdir(BACKUP_DIR) if f.startswith("deleted_unsolvable_")],
    reverse=True,
)
if not files:
    print("No backup found.")
    raise SystemExit(1)
latest = os.path.join(BACKUP_DIR, files[0])
print(f"Reading backup: {latest}")

with open(latest, "r", encoding="utf-8") as fp:
    rows = json.load(fp)
print(f"Backup contains {len(rows)} rows")

# True-broken markers (solution literally admits failure)
SOLUTION_BROKEN = [
    "задача не имеет решения",
    "задача не имеет решений",
    "решений не существует",
    "уточните, пожалуйста",
    "противоречие в условии",
    "условие задачи некорректно",
    "задача поставлена некорректно",
]

keep_deleted = []
restore = []
for r in rows:
    sol = (r.get("solution") or "").lower()
    matched = False
    for p in SOLUTION_BROKEN:
        if p in sol:
            matched = True
            break
    if matched:
        keep_deleted.append(r)
    else:
        restore.append(r)

print(f"Truly broken (keep deleted): {len(keep_deleted)}")
print(f"Will restore: {len(restore)}")

if not restore:
    print("Nothing to restore.")
    raise SystemExit(0)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cols = [
    "id", "class_level", "difficulty_level", "topic", "subtopic",
    "task_text", "solution", "criteria_1_point", "criteria_2_points",
    "created_at", "correct_answer", "is_flagged", "reports_count",
    "flagged_reason", "attempts_count", "solves_count", "actual_solve_rate",
    "suggested_level", "needs_reclassification", "last_calibrated_at",
    "needs_review", "llm_suggested_answer", "llm_suggested_solution",
    "review_reason", "review_flagged_at",
]
placeholders = ",".join(["?"] * len(cols))
col_list = ",".join(cols)

inserted = 0
for r in restore:
    values = [r.get(c) for c in cols]
    try:
        cur.execute(
            f"INSERT INTO adaptive_tasks ({col_list}) VALUES ({placeholders})",
            values,
        )
        inserted += 1
    except sqlite3.IntegrityError as e:
        print(f"  Skip id={r['id']} ({e})")

conn.commit()
print(f"Restored: {inserted}")

cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
print(f"Total tasks now: {cur.fetchone()[0]}")
conn.close()
