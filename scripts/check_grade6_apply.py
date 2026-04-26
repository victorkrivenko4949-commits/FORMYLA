# -*- coding: utf-8 -*-
import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('instance/formyla.db')
cur = conn.cursor()

print("=== PROVERKA POSLE REKALIBRATSII 6 KLASSA ===")

# 1. Raspredelenie original_grade=6 po novym klassam
print("\n1. Raspredelenie (original_grade=6):")
cur.execute("SELECT class_level, COUNT(*) FROM adaptive_tasks WHERE original_grade=6 GROUP BY class_level ORDER BY class_level")
for r in cur.fetchall():
    print(f"   class_level={r[0]}: {r[1]}")

# 2. Grade 7 - skol'ko s original_grade=7 vs original_grade=6
print("\n2. Grade 7 - otkuda prishli:")
cur.execute("SELECT original_grade, COUNT(*) FROM adaptive_tasks WHERE class_level=7 GROUP BY original_grade ORDER BY original_grade")
for r in cur.fetchall():
    og = r[0] if r[0] is not None else 'NULL (iskonno 7)'
    print(f"   original_grade={og}: {r[1]}")

# 3. Proverka: zadachi s original_grade=7 ne tronuto
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE original_grade=7")
g7_orig = cur.fetchone()[0]
print(f"\n3. Zadach s original_grade=7: {g7_orig} (dolzhno byt' 993)")

# 4. Difficulty anomalii v 6 klasse
cur.execute("SELECT difficulty_level, COUNT(*) FROM adaptive_tasks WHERE class_level=6 GROUP BY difficulty_level ORDER BY difficulty_level")
print("\n4. Difficulty v 6 klasse posle:")
for r in cur.fetchall():
    print(f"   diff={r[0]}: {r[1]}")

# 5. Anomalii difficulty > 5
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE original_grade=6 AND difficulty_level > 5")
anom = cur.fetchone()[0]
print(f"\n5. Anomalii difficulty > 5 (original_grade=6): {anom}")
if anom > 0:
    cur.execute("SELECT id, topic, difficulty_level, llm_suggested_difficulty, llm_quality_score FROM adaptive_tasks WHERE original_grade=6 AND difficulty_level > 5")
    for r in cur.fetchall():
        print(f"   ID={r[0]} | diff={r[2]} | llm_diff={r[3]} | q={r[4]} | {r[1]}")

conn.close()
print("\nDONE")
