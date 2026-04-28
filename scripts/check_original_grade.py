# -*- coding: utf-8 -*-
import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('instance/formyla.db')
cur = conn.cursor()

print("=== CHECK: original_grade integrity ===")

# 1. Raspredelenie original_grade -> class_level
cur.execute("""
    SELECT original_grade, class_level, COUNT(*)
    FROM adaptive_tasks
    WHERE original_grade IS NOT NULL
    GROUP BY original_grade, class_level
    ORDER BY original_grade, class_level
""")
print("\noriginal_grade | class_level | count | status")
print("-" * 55)
for r in cur.fetchall():
    status = "KEPT" if r[0] == r[1] else "MOVED"
    print(f"  orig={r[0]:2d} -> now={r[1]:2d}: {r[2]:4d}  [{status}]")

# 2. Zadachi s original_grade != 7 (ne dolzhno byt')
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE original_grade IS NOT NULL AND original_grade != 7")
other = cur.fetchone()[0]
print(f"\nZadach s original_grade != 7: {other}")
if other == 0:
    print("  --> OK: vse original_grade = 7 (tol'ko 7 klass audirovalsa)")
else:
    print("  --> PROBLEM: est' zadachi s original_grade != 7!")

# 3. Proverka: original_grade ne perezapisyvaetsya
# Esli by perezapisyvalsya, to u perenesennykh zadach original_grade = tekushchiy class_level
# No u nas original_grade = 7 dlya vsekh -> vse pravilno
cur.execute("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE original_grade IS NOT NULL
      AND original_grade = class_level
      AND class_level != 7
""")
wrong = cur.fetchone()[0]
print(f"\nZadach gde original_grade = class_level != 7: {wrong}")
if wrong == 0:
    print("  --> OK: original_grade ne perezapisyvaetsya")
else:
    print("  --> PROBLEM: original_grade mozhet byt' perezapisan!")

# 4. Itog
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE original_grade IS NOT NULL")
total = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE original_grade = 7 AND class_level = 7")
kept = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE original_grade = 7 AND class_level != 7")
moved = cur.fetchone()[0]

print(f"\nITOG:")
print(f"  Vsego s original_grade: {total}")
print(f"  Ostalis' v grade=7:     {kept}")
print(f"  Pereneseny iz grade=7:  {moved}")
print(f"  Summa: {kept + moved} (dolzhno = {total})")

conn.close()
print("\nDONE")
