#!/usr/bin/env python3
"""Quick verification that the bugfixes work correctly."""
import sqlite3

conn = sqlite3.connect('instance/formyla.db')
cur = conn.cursor()

# Test 1: Python-side max_n extraction for A1 G10 (should be 20)
cur.execute("SELECT id FROM method_tasks WHERE method_code = 'A1' AND grade = 10")
ids = [row[0] for row in cur.fetchall()]
max_n = max(int(id.rsplit('-', 1)[1]) for id in ids) if ids else 0
print(f"[TEST 1] A1 G10: max_n={max_n}, total={len(ids)} (CORRECT if max_n=20, total=20)")

# Test 2: F5 G9 (should be 23)
cur.execute("SELECT id FROM method_tasks WHERE method_code = 'F5' AND grade = 9")
ids = [row[0] for row in cur.fetchall()]
max_n = max(int(id.rsplit('-', 1)[1]) for id in ids) if ids else 0
print(f"[TEST 2] F5 G9: max_n={max_n}, total={len(ids)} (CORRECT if max_n=23, total=23)")

# Test 3: F7 G10 (should be 20 - from today's run, which may have overwritten nothing)
cur.execute("SELECT id FROM method_tasks WHERE method_code = 'F7' AND grade = 10")
ids = [row[0] for row in cur.fetchall()]
max_n = max(int(id.rsplit('-', 1)[1]) for id in ids) if ids else 0
print(f"[TEST 3] F7 G10: max_n={max_n}, total={len(ids)}")

# Test 4: Count all tasks per grade
for grade in [9, 10, 11]:
    cur.execute("SELECT COUNT(*) FROM method_tasks WHERE grade = ?", (grade,))
    cnt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT method_code) FROM method_tasks WHERE grade = ?", (grade,))
    methods = cur.fetchone()[0]
    print(f"[COUNT] Grade {grade}: {cnt} tasks across {methods} methods")

# Test 5: Find combos below target
print("\n[GAP ANALYSIS] Combos below 25 tasks:")
cur.execute("""
    SELECT grade, method_code, COUNT(*) as cnt
    FROM method_tasks
    GROUP BY grade, method_code
    HAVING cnt < 25
    ORDER BY grade, method_code
""")
rows = cur.fetchall()
for r in rows:
    print(f"  Grade {r[0]}, {r[1]}: {r[2]}/25 tasks")

conn.close()
