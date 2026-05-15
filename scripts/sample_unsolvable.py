"""Show samples of tasks where solution mentions 'не имеет решений' / similar
and check correct_answer field too."""
import sqlite3, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "instance", "formyla.db")

conn = sqlite3.connect(DB)
cur = conn.cursor()

# Tasks whose ANSWER says "нет решений", "невозможно" etc.
print("=== correct_answer indicates unsolvability ===")
ans_pat = (
    "WHERE correct_answer LIKE '%нет решений%' "
    "OR correct_answer LIKE '%не существует%' "
    "OR correct_answer LIKE '%невозможно%' "
    "OR correct_answer LIKE '%нельзя%' "
    "OR correct_answer LIKE '%не имеет реш%'"
)
cur.execute(f"SELECT COUNT(*) FROM adaptive_tasks {ans_pat}")
print(f"  count: {cur.fetchone()[0]}")
cur.execute(f"SELECT id, task_text, correct_answer FROM adaptive_tasks {ans_pat} LIMIT 5")
for rid, tt, ans in cur.fetchall():
    print(f"  id={rid}: TASK: {tt[:140]}")
    print(f"           ANS:  {ans[:80]}")

print("\n=== solution + task is a 'prove no solutions' (legit) vs broken ===")
# Look at solution - some are LEGIT (proof-style "докажите, что нет решений")
cur.execute(
    "SELECT id, task_text, solution FROM adaptive_tasks "
    "WHERE solution LIKE '%не имеет решений%' "
    "ORDER BY RANDOM() LIMIT 4"
)
for rid, tt, sol in cur.fetchall():
    print(f"--- id={rid} ---")
    print(f"TASK: {tt[:200]}")
    print(f"SOL : ...{sol[:400]}...")
    print()
