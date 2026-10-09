#!/usr/bin/env python3
"""Check cell task coverage in method_tasks vs course_entries."""
import sqlite3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('instance/formyla.db')
cur = conn.cursor()

print("=== MISSING & INCOMPLETE CELLS SUMMARY ===\n")

for grade in range(5, 12):
    cur.execute('SELECT method_code FROM vsosh_course_entries WHERE grade=?', (grade,))
    course_codes = set(r[0] for r in cur.fetchall())
    
    cur.execute('SELECT method_code FROM method_tasks WHERE grade=? GROUP BY method_code', (grade,))
    task_codes = set(r[0] for r in cur.fetchall())
    
    missing = sorted(course_codes - task_codes)
    
    cur.execute('SELECT method_code, COUNT(*) FROM method_tasks WHERE grade=? GROUP BY method_code HAVING COUNT(*) < 25', (grade,))
    incomplete = cur.fetchall()
    
    total_course = len(course_codes)
    total_tasks = len(task_codes)
    
    if missing or incomplete:
        print(f"--- Grade {grade} ---")
        print(f"  Course entries: {total_course}, Method tasks: {total_tasks}")
        for m in missing:
            print(f"  MISSING: {m} (0/25 tasks)")
        for code, cnt in incomplete:
            print(f"  INCOMPLETE: {code} ({cnt}/25 tasks)")
        print()

print("=== DIFFICULTY LEVELS IN method_tasks ===")
cur.execute('SELECT difficulty, COUNT(*) FROM method_tasks GROUP BY difficulty ORDER BY difficulty')
for row in cur.fetchall():
    print(f"  Level {row[0]}: {row[1]} tasks")

print()
cur.execute('SELECT COUNT(*) FROM method_tasks')
total = cur.fetchone()[0]
print(f"Total method_tasks: {total}")

cur.execute('SELECT COUNT(DISTINCT method_code || \":\" || grade) FROM method_tasks')
combos = cur.fetchone()[0]
print(f"Total (method,grade) combos covered: {combos}")

conn.close()
