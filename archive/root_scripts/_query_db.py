# -*- coding: utf-8 -*-
"""Task 1: Database facts — complete distributions."""
import sqlite3

conn = sqlite3.connect('formyla.db')
cur = conn.cursor()

print("=" * 60)
print("ADAPTIVE_TASKS (difficulty_level)")
print("=" * 60)
cur.execute("SELECT MIN(difficulty_level), MAX(difficulty_level) FROM adaptive_tasks")
r = cur.fetchone()
print(f"min={r[0]}, max={r[1]}")
cur.execute("SELECT difficulty_level, COUNT(*) FROM adaptive_tasks GROUP BY difficulty_level ORDER BY difficulty_level")
for r in cur.fetchall():
    print(f"  level {r[0]}: {r[1]}")

print()
print("=" * 60)
print("OLYMPIAD_TASKS (difficulty VARCHAR)")
print("=" * 60)
cur.execute("SELECT difficulty, COUNT(*) FROM olympiad_tasks GROUP BY difficulty ORDER BY difficulty")
for r in cur.fetchall():
    print(f"  difficulty='{r[0]}': {r[1]}")

print()
print("=" * 60)
print("GRADE_TASKS (level — bank)")
print("=" * 60)
cur.execute("SELECT MIN(level), MAX(level) FROM grade_tasks")
r = cur.fetchone()
print(f"min={r[0]}, max={r[1]}")
cur.execute("SELECT level, COUNT(*) FROM grade_tasks GROUP BY level ORDER BY level")
for r in cur.fetchall():
    print(f"  level {r[0]}: {r[1]}")

# Levels > 5 in grade_tasks
print()
cur.execute("SELECT COUNT(*) FROM grade_tasks WHERE level > 5")
print(f"grade_tasks level > 5: {cur.fetchone()[0]}")
cur.execute("SELECT level, COUNT(*) FROM grade_tasks WHERE level > 5 GROUP BY level ORDER BY level")
for r in cur.fetchall():
    print(f"  level {r[0]}: {r[1]}")

# Also check adaptive_tasks for levels > 5
print()
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE difficulty_level > 5")
print(f"adaptive_tasks difficulty_level > 5: {cur.fetchone()[0]}")

# Source distribution in grade_tasks
print()
cur.execute("SELECT source_id, COUNT(*) FROM grade_tasks GROUP BY source_id ORDER BY COUNT(*) DESC LIMIT 10")
for r in cur.fetchall():
    print(f"  source='{r[0]}': {r[1]}")

conn.close()
