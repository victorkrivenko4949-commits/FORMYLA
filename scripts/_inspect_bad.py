"""Inspect tasks containing the suspect Russian wording."""
import sqlite3, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "instance", "formyla.db")

# Reconfigure stdout for UTF-8 (Windows cmd safety)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PATTERNS = [
    "сколько решений",
    "Сколько решений",
    "число решений",
    "количество решений",
    "сколько различных",
    "имеет задача",
    "Сколько решен",
]

conn = sqlite3.connect(DB)
cur = conn.cursor()

for pat in PATTERNS:
    cur.execute(
        "SELECT id, class_level, difficulty_level, topic, "
        "substr(task_text, 1, 250) "
        "FROM adaptive_tasks WHERE task_text LIKE ? LIMIT 5",
        (f"%{pat}%",),
    )
    rows = cur.fetchall()
    print(f"\n=== pattern={pat!r} matches={len(rows)} ===")
    for r in rows:
        print(f"id={r[0]} cl={r[1]} L={r[2]} topic={r[3]}")
        print(f"  TEXT: {r[4]}")
        print()

# Also full count
cur.execute(
    "SELECT COUNT(*) FROM adaptive_tasks "
    "WHERE LOWER(task_text) LIKE '%сколько решений%' "
    "   OR LOWER(task_text) LIKE '%число решений%' "
    "   OR LOWER(task_text) LIKE '%количество решений%'"
)
print("\nTotal matches:", cur.fetchone()[0])
conn.close()
