#!/usr/bin/env python3
"""Export tasks for grades 9,10,11 with difficulty levels 6,7,8 only."""
import sqlite3
import json
from collections import Counter

conn = sqlite3.connect('instance/formyla.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute('''
    SELECT id, method_code, grade, num, difficulty,
           text, solution_idea, answer
    FROM method_tasks
    WHERE grade IN (9, 10, 11)
      AND difficulty IN (6, 7, 8)
    ORDER BY grade, method_code, num
''')

rows = [dict(r) for r in cur.fetchall()]
conn.close()

print(f"Total tasks exported: {len(rows)}")

# Count by grade and difficulty
by_grade_diff = Counter((r['grade'], r['difficulty']) for r in rows)
for (g, d), c in sorted(by_grade_diff.items()):
    print(f"  Grade {g}, Level {d}: {c} tasks")

with open('tasks_9_11.json', 'w', encoding='utf-8') as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)

print("Written to tasks_9_11.json")
