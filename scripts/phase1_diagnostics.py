# -*- coding: utf-8 -*-
"""
FAZA 1: Diagnostika zadach 7 klassa
Zapuskat iz kornya proekta: python scripts/phase1_diagnostics.py

Real'naya skhema adaptive_tasks:
  class_level     = klass (5-11)
  difficulty_level = slozhnost' (1-5)
  attempts_count  = kolichestvo popytok
  solves_count    = kolichestvo resheniy
  actual_solve_rate = real'nyy success rate
"""
import sqlite3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = 'instance/formyla.db'

def run(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    headers = [d[0] for d in cur.description]
    return rows, headers

def print_table(rows, headers):
    if not rows:
        print("  (net dannykh)")
        return
    widths = []
    for i, h in enumerate(headers):
        col_vals = [str(r[i]) if r[i] is not None else "NULL" for r in rows]
        widths.append(max(len(str(h)), max((len(v) for v in col_vals), default=0)))
    fmt = "  " + "  ".join("{{:<{}}}".format(w) for w in widths)
    print(fmt.format(*headers))
    print("  " + "  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt.format(*[str(x) if x is not None else "NULL" for x in row]))

conn = sqlite3.connect(DB_PATH)

print("=" * 70)
print("FAZA 1: DIAGNOSTIKA ZADACH 7 KLASSA")
print("Kolonki: class_level, difficulty_level, attempts_count, solves_count, actual_solve_rate")
print("=" * 70)

# 1.1 Bazovaya statistika
print("\n[1.1] BAZOVAYA STATISTIKA (class_level=7):")
rows, hdrs = run(conn, """
    SELECT 
        COUNT(*) as total,
        COUNT(DISTINCT topic) as topics,
        ROUND(AVG(difficulty_level), 2) as avg_diff,
        MIN(difficulty_level) as min_d,
        MAX(difficulty_level) as max_d,
        SUM(CASE WHEN is_flagged = 1 THEN 1 ELSE 0 END) as flagged,
        SUM(attempts_count) as total_attempts,
        SUM(solves_count) as total_solves,
        ROUND(AVG(CASE WHEN attempts_count > 0 THEN actual_solve_rate END), 3) as avg_solve_rate
    FROM adaptive_tasks WHERE class_level = 7
""")
print_table(rows, hdrs)

# 1.2 Raspredelenie po temam
print("\n[1.2] RASPREDELENIE PO TEMAM (class_level=7):")
rows, hdrs = run(conn, """
    SELECT 
        topic, 
        COUNT(*) as cnt,
        ROUND(AVG(difficulty_level), 2) as avg_diff,
        SUM(CASE WHEN difficulty_level >= 4 THEN 1 ELSE 0 END) as hard_cnt,
        SUM(CASE WHEN difficulty_level <= 2 THEN 1 ELSE 0 END) as easy_cnt,
        SUM(attempts_count) as attempts,
        ROUND(AVG(CASE WHEN attempts_count > 0 THEN actual_solve_rate END), 3) as avg_sr
    FROM adaptive_tasks WHERE class_level = 7
    GROUP BY topic ORDER BY cnt DESC
""")
print_table(rows, hdrs)

# 1.3 Raspredelenie slozhnosti
print("\n[1.3] RASPREDELENIE SLOZHNOSTI (class_level=7):")
rows, hdrs = run(conn, """
    SELECT 
        difficulty_level,
        COUNT(*) as cnt,
        ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=7), 1) as pct,
        ROUND(AVG(CASE WHEN attempts_count > 0 THEN actual_solve_rate END), 3) as avg_sr
    FROM adaptive_tasks WHERE class_level = 7
    GROUP BY difficulty_level ORDER BY difficulty_level
""")
print_table(rows, hdrs)

# 1.4 Vse tablicy v BD
print("\n[1.4] VSE TABLICY V BD:")
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
all_tables = [r[0] for r in cur.fetchall()]
print("  " + ", ".join(all_tables))

# Skhema tablic statistiki
stat_keywords = ['answer', 'attempt', 'stat', 'result', 'session', 'progress', 'history', 'log', 'tutor']
stat_tables = [t for t in all_tables if any(k in t.lower() for k in stat_keywords)]
print("\n  Tablicy pokhozhe na statistiku: " + (", ".join(stat_tables) if stat_tables else "NE NAYDENO"))

for tbl in stat_tables:
    print("\n  Skhema '{}':".format(tbl))
    cur.execute("PRAGMA table_info({})".format(tbl))
    cols = cur.fetchall()
    col_names = [c[1] for c in cols]
    print("    Kolonki: " + ", ".join(col_names))
    cur.execute("SELECT COUNT(*) FROM {}".format(tbl))
    cnt = cur.fetchone()[0]
    print("    Strok: {}".format(cnt))

# 1.5 Zadachi s real'noy statistikoy (attempts_count >= 3)
print("\n[1.5] TOP-30 SAMYKH NERESHAEMYKH ZADACH 7 KLASSA (attempts >= 3):")
rows, hdrs = run(conn, """
    SELECT 
        id, topic, difficulty_level as diff,
        attempts_count as att,
        solves_count as solves,
        ROUND(actual_solve_rate, 3) as sr,
        SUBSTR(task_text, 1, 60) as preview
    FROM adaptive_tasks
    WHERE class_level = 7 AND attempts_count >= 3
    ORDER BY actual_solve_rate ASC
    LIMIT 30
""")
if rows:
    print_table(rows, hdrs)
    print("\n  Vsego zadach 7 klassa s attempts >= 3: {}".format(len(rows)))
else:
    print("  Net zadach s attempts >= 3.")
    print("  --> PLAN B: LLM-ocenka slozhnosti vmesto real'noy statistiki.")

# Dopolnitel'no: zadachi s attempts >= 1
print("\n[1.5b] STATISTIKA PO ZADACHAM 7 KLASSA (lyubye attempts):")
rows2, hdrs2 = run(conn, """
    SELECT 
        COUNT(*) as total_tasks,
        SUM(CASE WHEN attempts_count = 0 THEN 1 ELSE 0 END) as no_attempts,
        SUM(CASE WHEN attempts_count >= 1 THEN 1 ELSE 0 END) as has_attempts,
        SUM(CASE WHEN attempts_count >= 3 THEN 1 ELSE 0 END) as enough_attempts,
        SUM(CASE WHEN actual_solve_rate IS NOT NULL THEN 1 ELSE 0 END) as has_sr
    FROM adaptive_tasks WHERE class_level = 7
""")
print_table(rows2, hdrs2)

# Primery zadach po slozhnosti
print("\n[PRIMERY] PRIMERY ZADACH 7 KLASSA (po 2 na kazhdyy uroven'):")
for diff in [1, 2, 3, 4, 5]:
    rows, hdrs = run(conn, """
        SELECT id, topic, difficulty_level as diff, 
               attempts_count as att, ROUND(actual_solve_rate,2) as sr,
               SUBSTR(task_text, 1, 80) as preview, correct_answer
        FROM adaptive_tasks WHERE class_level = 7 AND difficulty_level = ?
        ORDER BY attempts_count DESC
        LIMIT 2
    """, (diff,))
    if rows:
        print("\n  --- Difficulty {} ---".format(diff))
        print_table(rows, hdrs)

conn.close()
print("\n" + "=" * 70)
print("DIAGNOSTIKA ZAVERSHENA")
print("=" * 70)
