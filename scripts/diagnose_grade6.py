# -*- coding: utf-8 -*-
"""
Diagnostika zadach 6 klassa — tol'ko SELECT, bez izmeneniy BD
python scripts/diagnose_grade6.py
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
# 1. Obshchee kolichestvo zadach 6 klassa
# ============================================================
sep("1. OBSHCHEE KOLICHESTVO ZADACH (class_level=6)")
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=6")
total = cur.fetchone()[0]
print(f"  Vsego zadach 6 klassa: {total}")

# ============================================================
# 2. Raspredelenie po difficulty
# ============================================================
sep("2. RASPREDELENIE PO DIFFICULTY")
cur.execute("""
    SELECT difficulty_level, COUNT(*) as cnt,
           ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=6),1) as pct
    FROM adaptive_tasks WHERE class_level=6
    GROUP BY difficulty_level ORDER BY difficulty_level
""")
print(f"  {'Diff':>5}  {'Count':>6}  {'%':>6}  {'Bar'}")
print(f"  {'-'*5}  {'-'*6}  {'-'*6}  {'-'*20}")
for r in cur.fetchall():
    bar = '#' * int(r[2]/2)
    print(f"  {r[0]:>5}  {r[1]:>6}  {r[2]:>5.1f}%  {bar}")

# ============================================================
# 3. Raspredelenie po temam
# ============================================================
sep("3. RASPREDELENIE PO TEMAM")
cur.execute("""
    SELECT topic, COUNT(*) as cnt,
           ROUND(AVG(difficulty_level),2) as avg_diff
    FROM adaptive_tasks WHERE class_level=6
    GROUP BY topic ORDER BY cnt DESC
""")
rows = cur.fetchall()
print(f"  {'Topic':50s}  {'Cnt':>5}  {'AvgD':>5}")
print(f"  {'-'*50}  {'-'*5}  {'-'*5}")
for r in rows:
    topic_short = r[0][:50] if r[0] else 'NULL'
    print(f"  {topic_short:50s}  {r[1]:>5}  {r[2]:>5}")

# ============================================================
# 4. Zadachi s original_grade != NULL (prishli iz drugogo klassa)
# ============================================================
sep("4. ZADACHI S original_grade != NULL (iz drugogo klassa)")
cur.execute("""
    SELECT original_grade, COUNT(*)
    FROM adaptive_tasks WHERE class_level=6
    GROUP BY original_grade ORDER BY original_grade
""")
rows4 = cur.fetchall()
if rows4:
    for r in rows4:
        og = r[0] if r[0] is not None else 'NULL (iskonno 6 klass)'
        print(f"  original_grade={og}: {r[1]} zadach")
else:
    print("  (net dannykh)")

# ============================================================
# 5. Primery zadach D1, D3, D5
# ============================================================
sep("5. PRIMERY ZADACH PO DIFFICULTY (po 3 na D1/D3/D5)")
for diff in [1, 3, 5]:
    cur.execute("""
        SELECT id, topic, difficulty_level, SUBSTR(task_text, 1, 150) as preview, correct_answer
        FROM adaptive_tasks
        WHERE class_level=6 AND difficulty_level=?
        ORDER BY RANDOM() LIMIT 3
    """, (diff,))
    rows5 = cur.fetchall()
    print(f"\n  --- Difficulty {diff} ---")
    for r in rows5:
        print(f"  ID={r[0]} | [{r[2]}] | {r[1]}")
        print(f"    Task: {r[3]}")
        print(f"    Ans:  {r[4]}")

# ============================================================
# 6. Sravnenie s programmoy 6 klassa RF
# ============================================================
sep("6. SRAVNENIE S PROGRAMMOY 6 KLASSA RF")

# Temy programmy 6 klassa i klyuchevye slova dlya poiska
program_topics = {
    'Drobi (obyknovennye)':     ['дроби', 'доли', 'дробь'],
    'Desyatichnye drobi':       ['десятичн'],
    'Protsenty i proportsii':   ['процент', 'пропорц'],
    'Otricatel\'nye chisla':    ['отрицательн', 'целые числа'],
    'Modul\' chisla':           ['модуль'],
    'Koordinatnaya ploskost\'': ['координат'],
    'Lineynye uravneniya':      ['уравнен', 'линейн'],
    'Zadachi na dvizhenie':     ['движен', 'скорость', 'текстовые задачи'],
    'Geometriya (baza)':        ['геометрия', 'периметр', 'площадь', 'угол', 'треугольник'],
    'Delimost\', NOD/NOK':      ['делимость', 'нод', 'нок', 'признаки делимости'],
    'Kombinatorika (baza)':     ['комбинаторика', 'правило суммы', 'правило произведения'],
    'Logika/Invarianty':        ['логика', 'инвариант', 'рыцари', 'лжец'],
    'Grafy':                    ['граф', 'знакомств', 'турнир'],
    'Razrezaniya':              ['разрезани', 'замощени'],
}

cur.execute("SELECT topic, COUNT(*) FROM adaptive_tasks WHERE class_level=6 GROUP BY topic")
all_topics_6 = {r[0]: r[1] for r in cur.fetchall()}

print(f"\n  {'Tema programmy':35s}  {'Zadach v BD':>12}  {'Status'}")
print(f"  {'-'*35}  {'-'*12}  {'-'*15}")
for prog_topic, keywords in program_topics.items():
    count = 0
    matched_topics = []
    for db_topic, db_count in all_topics_6.items():
        if db_topic and any(kw.lower() in db_topic.lower() for kw in keywords):
            count += db_count
            matched_topics.append(db_topic[:30])
    
    if count == 0:
        status = 'OTSUTSTVUET'
    elif count < 30:
        status = f'MALO ({count})'
    else:
        status = f'OK ({count})'
    
    print(f"  {prog_topic:35s}  {count:>12}  {status}")

# ============================================================
# 7. Sostoyanie BD
# ============================================================
sep("7. SOSTOYANIE BD")
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print(f"  Vsego tablic: {len(tables)}")
profile_tables = ['user_test_history', 'user_task_progress', 'user_achievements', 'user_xp_log']
for t in profile_tables:
    status = 'SOZDANA' if t in tables else 'NE SOZDANA'
    print(f"  {t}: {status}")

import os, datetime
stat = os.stat(DB_PATH)
mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
size_mb = stat.st_size / 1024 / 1024
print(f"\n  formyla.db: {size_mb:.1f} MB")
print(f"  Posled. izmenenie: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")

conn.close()
print("\n" + "=" * 65)
print("DIAGNOSTIKA ZAVERSHENA")
print("=" * 65)
