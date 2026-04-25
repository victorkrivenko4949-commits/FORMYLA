# -*- coding: utf-8 -*-
"""
Glubokiy audit zadach 7 klassa
python scripts/deep_audit.py
"""
import sqlite3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = 'instance/formyla.db'
conn = sqlite3.connect(DB_PATH)

def run(sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    headers = [d[0] for d in cur.description]
    return rows, headers

def sep(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

# ============================================================
# PROVERKA 1: Difficulty 6 i 7
# ============================================================
sep("PROVERKA 1a: 5 PRIMEROV DIFFICULTY=7 (class_level=7)")
rows, _ = run("""
    SELECT id, topic, difficulty_level, correct_answer,
           task_text,
           SUBSTR(COALESCE(solution,'NULL'), 1, 100) as solution_preview
    FROM adaptive_tasks
    WHERE class_level=7 AND difficulty_level=7
    ORDER BY RANDOM() LIMIT 5
""")
for r in rows:
    print("\n--- ID={} | Topic: {} | Diff: {} ---".format(r[0], r[1], r[2]))
    print("  Answer: {}".format(r[3]))
    print("  Task:   {}".format(r[4][:300] if r[4] else 'NULL'))
    print("  Sol:    {}".format(r[5]))

sep("PROVERKA 1b: 10 PRIMEROV DIFFICULTY=6 (class_level=7)")
rows, _ = run("""
    SELECT id, topic, difficulty_level, correct_answer,
           task_text
    FROM adaptive_tasks
    WHERE class_level=7 AND difficulty_level=6
    ORDER BY RANDOM() LIMIT 10
""")
for r in rows:
    print("\n--- ID={} | Topic: {} | Diff: {} ---".format(r[0], r[1], r[2]))
    print("  Answer: {}".format(r[3]))
    print("  Task:   {}".format(r[4][:250] if r[4] else 'NULL'))

# ============================================================
# PROVERKA 2: Difficulty=1 anomalii
# ============================================================
sep("PROVERKA 2: 10 PRIMEROV DIFFICULTY=1 (class_level=7)")
rows, _ = run("""
    SELECT id, topic, difficulty_level, correct_answer, task_text
    FROM adaptive_tasks
    WHERE class_level=7 AND difficulty_level=1
    ORDER BY RANDOM() LIMIT 10
""")
for r in rows:
    print("\n--- ID={} | Topic: {} | Diff: {} ---".format(r[0], r[1], r[2]))
    print("  Answer: {}".format(r[3]))
    print("  Task:   {}".format(r[4][:250] if r[4] else 'NULL'))

# ============================================================
# PROVERKA 3: Matrica "tema x difficulty = primer"
# ============================================================
sep("PROVERKA 3: MATRICA TEMA x DIFFICULTY (1 primer na kazhdyy)")
rows_topics, _ = run("""
    SELECT DISTINCT topic FROM adaptive_tasks WHERE class_level=7 ORDER BY topic
""")
topics = [r[0] for r in rows_topics]

for topic in topics:
    print("\n  TEMA: {}".format(topic))
    for diff in [1, 2, 3, 4, 5, 6, 7]:
        rows, _ = run("""
            SELECT id, difficulty_level, SUBSTR(task_text, 1, 100) as preview, correct_answer
            FROM adaptive_tasks
            WHERE class_level=7 AND topic=? AND difficulty_level=?
            ORDER BY RANDOM() LIMIT 1
        """, (topic, diff))
        if rows:
            r = rows[0]
            print("    [D{}] ID={} | Ans: {} | {}".format(
                diff, r[0], r[3], r[2]))

# ============================================================
# PROVERKA 4: Pochemu attempts=0, statistika pol'zovateley
# ============================================================
sep("PROVERKA 4: STATISTIKA POL'ZOVATELEY")

rows, _ = run("SELECT COUNT(*) as users_total FROM users")
print("  Vsego pol'zovateley: {}".format(rows[0][0]))

# Vse tablicy
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
all_tables = [r[0] for r in cur.fetchall()]
print("\n  Vse tablicy: " + ", ".join(all_tables))

# Proverka kazhdoy tablicy na nalichie task_id
print("\n  Proverka tablic na nalichie task_id:")
for tbl in all_tables:
    cur.execute("PRAGMA table_info({})".format(tbl))
    cols = [c[1].lower() for c in cur.fetchall()]
    if 'task_id' in cols or 'problem_id' in cols:
        cur.execute("SELECT COUNT(*) FROM {}".format(tbl))
        cnt = cur.fetchone()[0]
        print("    {} -> kolonki: {} | strok: {}".format(tbl, ", ".join(cols), cnt))

# adaptive_test_results - podrobnee
print("\n  Podrobno adaptive_test_results:")
rows, hdrs = run("SELECT * FROM adaptive_test_results LIMIT 3")
if rows:
    for r in rows:
        for h, v in zip(hdrs, r):
            print("    {}: {}".format(h, str(v)[:100]))
        print()
else:
    print("    (pusta)")

# tutor_calls - podrobnee
print("\n  Podrobno tutor_calls (pervye 3):")
rows, hdrs = run("SELECT * FROM tutor_calls LIMIT 3")
if rows:
    for r in rows:
        for h, v in zip(hdrs, r):
            print("    {}: {}".format(h, str(v)[:100]))
        print()
else:
    print("    (pusta)")

# Proverka: est' li v adaptive_tasks zadachi kotorye kogda-libo
# ispol'zovalis' v testakh
print("\n  Proverka adaptive_test_problems:")
rows, hdrs = run("SELECT * FROM adaptive_test_problems LIMIT 5")
if rows:
    print("  Kolonki: " + ", ".join(hdrs))
    for r in rows:
        print("  " + str(r))
else:
    print("  (pusta)")

# Proverka: est' li svyaz' mezhdu adaptive_tasks i adaptive_test_problems
cur.execute("PRAGMA table_info(adaptive_test_problems)")
atp_cols = [c[1] for c in cur.fetchall()]
print("\n  adaptive_test_problems kolonki: " + ", ".join(atp_cols))

cur.execute("SELECT COUNT(*) FROM adaptive_test_problems")
print("  adaptive_test_problems strok: {}".format(cur.fetchone()[0]))

# Proverka: est' li v adaptive_tasks zadachi s class_level=7 kotorye
# vstrechayutsya v adaptive_test_problems
if 'task_id' in [c.lower() for c in atp_cols]:
    rows, _ = run("""
        SELECT COUNT(*) FROM adaptive_test_problems atp
        JOIN adaptive_tasks at ON atp.task_id = at.id
        WHERE at.class_level = 7
    """)
    print("  Zadach 7 klassa v adaptive_test_problems: {}".format(rows[0][0]))

conn.close()
print("\n" + "=" * 70)
print("GLUBOKIY AUDIT ZAVERSHEN")
print("=" * 70)
