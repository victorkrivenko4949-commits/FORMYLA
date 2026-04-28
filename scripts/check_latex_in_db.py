# -*- coding: utf-8 -*-
import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('instance/formyla.db')
cur = conn.cursor()

print("=== CHECK: LaTeX v task_text ===")

# Naydti zadachi s LaTeX formulami
cur.execute("SELECT id, topic, task_text FROM adaptive_tasks WHERE task_text LIKE '%frac%' OR task_text LIKE '%\\(%' LIMIT 5")
rows = cur.fetchall()
print(f"Zadach s 'frac' ili '\\(': {len(rows)}")
for r in rows:
    print(f"\nID={r[0]} | {r[1]}")
    print(f"  repr: {repr(r[2][:200])}")

# Proverit' kak Jinja2 peredaet stroku
# Esli v BD: \frac -> v HTML dolzhno byt' \frac (ne rac)
# Esli v BD: \\frac -> v HTML budet \frac (posle Jinja2 escape)
print("\n=== PRIMER ZADACHI S FORMULOY ===")
cur.execute("SELECT id, task_text FROM adaptive_tasks WHERE class_level=6 AND task_text LIKE '%\\\\(%' LIMIT 1")
rows2 = cur.fetchall()
if rows2:
    print(f"ID={rows2[0][0]}")
    print(f"repr: {repr(rows2[0][1][:300])}")
else:
    # Prosto pervaya zadacha 6 klassa
    cur.execute("SELECT id, task_text FROM adaptive_tasks WHERE class_level=6 LIMIT 1")
    r = cur.fetchone()
    if r:
        print(f"ID={r[0]}")
        print(f"repr: {repr(r[1][:300])}")

conn.close()
print("\nDONE")
