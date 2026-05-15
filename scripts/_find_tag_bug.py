"""Find tasks whose solution contains stray \\tag or unwrapped \\frac etc."""
import sqlite3, os, sys, re

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "instance", "formyla.db")

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 1) Find the AB || A1B1 task in geometry
cur.execute(
    "SELECT id, class_level, difficulty_level, topic, "
    "substr(task_text, 1, 200), substr(solution, 1, 800) "
    "FROM adaptive_tasks "
    "WHERE task_text LIKE '%AA_1%' AND task_text LIKE '%BB_1%' "
    "AND task_text LIKE '%высот%' "
    "LIMIT 10"
)
for r in cur.fetchall():
    print(f"\n=== id={r[0]} cl={r[1]} L={r[2]} topic={r[3]} ===")
    print("TEXT:", r[4])
    print("SOL :", r[5])

print("\n\n=== Tasks with \\tag in solution ===")
cur.execute(
    "SELECT id, class_level, difficulty_level, topic FROM adaptive_tasks "
    "WHERE solution LIKE '%\\\\tag%' OR task_text LIKE '%\\\\tag%' LIMIT 20"
)
rows = cur.fetchall()
print(f"Found {len(rows)} with \\tag")
for r in rows:
    print(f"  id={r[0]} cl={r[1]} L={r[2]} topic={r[3]}")

# Count various other LaTeX-outside-delimiters issues
patterns = [
    ("\\\\frac{", "\\frac without delimiter check"),
    ("\\\\angle", "\\angle"),
    ("\\\\triangle", "\\triangle"),
    ("\\\\cdot", "\\cdot"),
    ("\\\\sqrt", "\\sqrt"),
]
print("\n=== Total task counts with these LaTeX commands ===")
for p, label in patterns:
    cur.execute(f"SELECT COUNT(*) FROM adaptive_tasks WHERE solution LIKE '%{p}%'")
    print(f"  {label}: {cur.fetchone()[0]}")

conn.close()
