#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
conn = sqlite3.connect('instance/formyla.db')
conn.text_factory = str
c = conn.cursor()

print("=== VserossCourseEntries summary ===")
c.execute("SELECT grade, stage, COUNT(*) FROM vsosh_course_entries GROUP BY grade, stage ORDER BY grade, stage")
for r in c.fetchall():
    print(f"  grade={r[0]}, stage={r[1]}, count={r[2]}")

print()
print("=== Total cells per grade ===")
c.execute("SELECT grade, COUNT(*) FROM vsosh_course_entries GROUP BY grade ORDER BY grade")
for r in c.fetchall():
    print(f"  grade={r[0]}: {r[1]} cells")

print()
print("=== MethodTasks count ===")
c.execute("SELECT COUNT(*) FROM method_tasks")
print(f"  Total tasks: {c.fetchone()[0]}")

c.execute("SELECT grade, COUNT(*) FROM method_tasks GROUP BY grade ORDER BY grade")
for r in c.fetchall():
    print(f"  grade={r[0]}: {r[1]} tasks")

print()
print("=== MethodTasks per method_code ===")
c.execute("SELECT method_code, COUNT(*) as cnt FROM method_tasks GROUP BY method_code ORDER BY cnt DESC")
for r in c.fetchall()[:15]:
    print(f"  code={r[0]}: {r[1]} tasks")

print()
print("=== Unique method_codes in cells vs tasks ===")
c.execute("SELECT DISTINCT method_code FROM vsosh_course_entries")
cell_codes = set(r[0] for r in c.fetchall())
c.execute("SELECT DISTINCT method_code FROM method_tasks")
task_codes = set(r[0] for r in c.fetchall())
print(f"  Codes in cells: {len(cell_codes)}")
print(f"  Codes in tasks: {len(task_codes)}")
print(f"  Codes in cells but NOT in tasks: {sorted(cell_codes - task_codes)}")
print(f"  Codes in tasks but NOT in cells: {sorted(task_codes - cell_codes)}")

print()
print("=== Unique stages ===")
c.execute("SELECT DISTINCT stage FROM vsosh_course_entries ORDER BY stage")
for r in c.fetchall():
    print(f"  stage={r[0]}")

conn.close()
