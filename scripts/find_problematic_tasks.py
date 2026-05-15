"""Find adaptive tasks that are likely problematic:
- contain wording like "сколько решений", "число решений" — leads to ambiguity
- solution says "не имеет решений", "задача не имеет", "нет решений" — unsolvable
"""
import sqlite3, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "instance", "formyla.db")

# patterns that indicate "how many solutions" wording (we want to drop)
COUNT_PATTERNS = [
    "сколько решений",
    "сколько различных решений",
    "число решений",
    "количество решений",
    "сколько способов",   # combinatorial counting tasks are OK if not "find all"
]
# patterns in solution that indicate the task is unsolvable as posed
UNSOLVABLE_PATTERNS = [
    "не имеет решений",
    "нет решений",
    "задача не имеет",
    "уточните, пожалуйста",
    "не существует точки",
    "невозможно построить",
    "не существует такого",
]

conn = sqlite3.connect(DB)
cur = conn.cursor()

print("=== 'count of solutions' wording in task_text ===")
total_count = 0
for p in COUNT_PATTERNS:
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text LIKE ?", (f"%{p}%",))
    n = cur.fetchone()[0]
    print(f"  {p:35s}: {n}")
    total_count += n

print("\n=== 'unsolvable' wording in solution ===")
total_unsolv = 0
for p in UNSOLVABLE_PATTERNS:
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE solution LIKE ?", (f"%{p}%",))
    n = cur.fetchone()[0]
    print(f"  {p:35s}: {n}")
    total_unsolv += n

print("\n=== Distinct ids matching ANY problematic pattern ===")
where = " OR ".join(
    ["task_text LIKE ?"] * len(COUNT_PATTERNS) +
    ["solution LIKE ?"] * len(UNSOLVABLE_PATTERNS)
)
params = [f"%{p}%" for p in COUNT_PATTERNS] + [f"%{p}%" for p in UNSOLVABLE_PATTERNS]
cur.execute(f"SELECT id, class_level, difficulty_level, topic, task_text FROM adaptive_tasks WHERE {where}", params)
rows = cur.fetchall()
print(f"TOTAL: {len(rows)}")
print("\nFirst 5 examples:")
for rid, cl, dl, tp, tt in rows[:5]:
    print(f"  id={rid} g{cl} L{dl} [{tp[:30]}]: {tt[:120]}…")
