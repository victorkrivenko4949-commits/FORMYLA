# -*- coding: utf-8 -*-
"""
Diagnostika: Rytsari i lzhetsy, 5 klass, status vsekh klassov
python scripts/diagnose_all_classes.py
"""
import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = 'instance/formyla.db'
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

def sep(title):
    print("\n" + "=" * 65)
    print(title)
    print("=" * 65)

# ============================================================
# 1. Rytsari i lzhetsy
# ============================================================
sep("1. RYTSARI I LZHETSY — raspredelenie po klassam")
cur.execute("""
    SELECT class_level, original_grade, difficulty_level, COUNT(*) as cnt
    FROM adaptive_tasks
    WHERE topic LIKE '%рыцар%' OR topic LIKE '%лжец%'
    GROUP BY class_level, original_grade, difficulty_level
    ORDER BY class_level, difficulty_level
""")
rows = cur.fetchall()
print(f"  class_level | original_grade | difficulty | count")
print(f"  {'-'*55}")
for r in rows:
    og = str(r[1]) if r[1] is not None else 'NULL'
    print(f"  {r[0]:11d} | {og:14s} | {r[2]:10d} | {r[3]}")

print("\n  5 primerov zadach:")
cur.execute("""
    SELECT id, class_level, difficulty_level, SUBSTR(task_text, 1, 120) as preview
    FROM adaptive_tasks
    WHERE topic LIKE '%рыцар%' OR topic LIKE '%лжец%'
    ORDER BY class_level, RANDOM()
    LIMIT 5
""")
for r in cur.fetchall():
    print(f"\n  ID={r[0]} | class={r[1]} | diff={r[2]}")
    print(f"  {r[3]}")

# ============================================================
# 2. Diagnostika 5 klassa
# ============================================================
sep("2. DIAGNOSTIKA 5 KLASSA")

cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=5")
total5 = cur.fetchone()[0]
print(f"  Vsego zadach 5 klassa: {total5}")

print("\n  Raspredelenie po difficulty:")
cur.execute("""
    SELECT difficulty_level, COUNT(*) as cnt,
           ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=5),1) as pct
    FROM adaptive_tasks WHERE class_level=5
    GROUP BY difficulty_level ORDER BY difficulty_level
""")
for r in cur.fetchall():
    print(f"    diff={r[0]}: {r[1]} ({r[2]}%)")

print("\n  Raspredelenie po temam:")
cur.execute("""
    SELECT topic, COUNT(*) as cnt, ROUND(AVG(difficulty_level),2) as avg_diff
    FROM adaptive_tasks WHERE class_level=5
    GROUP BY topic ORDER BY cnt DESC
""")
for r in cur.fetchall():
    print(f"    [{r[0]}]: {r[1]} zadach, avg_diff={r[2]}")

cur.execute("""
    SELECT original_grade, COUNT(*) FROM adaptive_tasks
    WHERE class_level=5
    GROUP BY original_grade ORDER BY original_grade
""")
print("\n  original_grade (est' li uzhe rekalibrovanye):")
for r in cur.fetchall():
    og = str(r[0]) if r[0] is not None else 'NULL (iskonno 5 klass)'
    print(f"    original_grade={og}: {r[1]}")

# ============================================================
# 3. Status vsekh klassov
# ============================================================
sep("3. STATUS VSEKH KLASSOV POSLE SEGODNYASHNIKH RABOT")
cur.execute("""
    SELECT class_level,
           COUNT(*) AS total,
           SUM(CASE WHEN original_grade IS NOT NULL THEN 1 ELSE 0 END) AS recalibrated,
           ROUND(AVG(difficulty_level), 2) AS avg_diff,
           MIN(difficulty_level) as min_diff,
           MAX(difficulty_level) as max_diff
    FROM adaptive_tasks
    GROUP BY class_level
    ORDER BY class_level
""")
rows = cur.fetchall()
print(f"  {'class':>6} | {'total':>6} | {'recalib':>8} | {'avg_diff':>8} | {'min':>4} | {'max':>4}")
print(f"  {'-'*55}")
for r in rows:
    print(f"  {r[0]:>6} | {r[1]:>6} | {r[2]:>8} | {r[3]:>8} | {r[4]:>4} | {r[5]:>4}")

# Dopolnitelno: skol'ko zadach s original_grade po klassam
print("\n  Zadachi s original_grade (otkuda prishli):")
cur.execute("""
    SELECT original_grade, class_level, COUNT(*) as cnt
    FROM adaptive_tasks
    WHERE original_grade IS NOT NULL
    GROUP BY original_grade, class_level
    ORDER BY original_grade, class_level
""")
for r in cur.fetchall():
    arrow = "->" if r[0] != r[1] else "=="
    print(f"    orig={r[0]} {arrow} now={r[1]}: {r[2]} zadach")

conn.close()
print("\n" + "=" * 65)
print("DIAGNOSTIKA ZAVERSHENA")
print("=" * 65)
