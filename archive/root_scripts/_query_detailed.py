#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3, sys

conn = sqlite3.connect('instance/formyla.db')
# Use proper text factory for UTF-8
conn.text_factory = lambda x: x.decode('utf-8', errors='replace')
c = conn.cursor()

# Get stages with proper encoding
c.execute("SELECT DISTINCT stage FROM vsosh_course_entries ORDER BY stage")
stages = [r[0] for r in c.fetchall()]
print("=== Stages found ===")
for s in stages:
    print(f"  '{s}'")

print()
print("=== All VserossCourseEntry cells ===")
c.execute("""
  SELECT grade, stage, method_code, method_name, section, study_order, importance
  FROM vsosh_course_entries
  ORDER BY grade, stage, study_order
""")
rows = c.fetchall()
for r in rows:
    method_name = r[3] if r[3] else "?"
    print(f"  gr={r[0]} | st={r[1]} | code={r[2]:6s} | name={method_name[:45]:45s} | sec={r[4]:1s} | ord={r[5]} | imp={r[6]}")

print()
print(f"Total cells: {len(rows)}")

print()
print("=== MethodTasks summary ===")
c.execute("SELECT COUNT(*) FROM method_tasks")
total = c.fetchone()[0]
print(f"Total tasks: {total}")

c.execute("SELECT grade, COUNT(*) FROM method_tasks GROUP BY grade ORDER BY grade")
for r in c.fetchall():
    print(f"  grade={r[0]}: {r[1]} tasks")

print()
print("=== MethodTasks per method_code+grade ===")
c.execute("SELECT method_code, grade, COUNT(*) FROM method_tasks GROUP BY method_code, grade ORDER BY method_code, grade")
for r in c.fetchall():
    print(f"  code={r[0]:6s} grade={r[1]}: {r[2]} tasks")

print()
print("=== Cells with task counts (LEFT JOIN MethodTasks) ===")
c.execute("""
  SELECT e.grade, e.stage, e.method_code, e.method_name, COUNT(m.id) as task_count
  FROM vsosh_course_entries e
  LEFT JOIN method_tasks m ON m.method_code = e.method_code AND m.grade = e.grade
  GROUP BY e.grade, e.stage, e.method_code
  ORDER BY e.grade, e.stage, e.study_order
""")
for r in c.fetchall():
    print(f"  gr={r[0]} | st={r[1]} | code={r[2]:6s} | name={(r[3] or '?')[:35]:35s} | tasks={r[4]}")

print()
print("=== Cells that have ZERO tasks ===")
c.execute("""
  SELECT e.grade, e.stage, e.method_code, e.method_name
  FROM vsosh_course_entries e
  LEFT JOIN method_tasks m ON m.method_code = e.method_code AND m.grade = e.grade
  WHERE m.id IS NULL
  ORDER BY e.grade, e.stage, e.study_order
""")
zero_rows = c.fetchall()
print(f"Count: {len(zero_rows)} cells with zero tasks")
for r in zero_rows:
    print(f"  gr={r[0]} | st={r[1]} | code={r[2]:6s} | name={(r[3] or '?')[:40]}")

print()
print("=== MethodTasks: sample with stage column ===")
c.execute("SELECT id, grade, method_code, stage, difficulty, difficulty_label FROM method_tasks LIMIT 10")
for r in c.fetchall():
    print(f"  id={r[0]} | gr={r[1]} | code={r[2]} | stage={r[3]} | diff={r[4]} | label={r[5]}")

conn.close()
