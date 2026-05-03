#!/usr/bin/env python3
"""Export all movement tasks from Render PostgreSQL to JSON file."""
import psycopg2, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PG_URL = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'

print('Connecting...')
conn = psycopg2.connect(PG_URL, connect_timeout=15)
cur = conn.cursor()

cur.execute("""
    SELECT id, class_level, difficulty_level, topic, task_text, correct_answer, solution
    FROM adaptive_tasks 
    WHERE topic = 'Задачи на движение'
    ORDER BY class_level, difficulty_level, id
""")

columns = ['id', 'class_level', 'difficulty_level', 'topic', 'task_text', 'correct_answer', 'solution']
rows = cur.fetchall()
conn.close()

print(f'Exported {len(rows)} movement tasks')

# Convert to list of dicts
tasks = []
for row in rows:
    task = {}
    for i, col in enumerate(columns):
        val = row[i]
        if hasattr(val, 'isoformat'):
            val = val.isoformat()
        task[col] = val
    tasks.append(task)

# Count by grade
from collections import Counter
grade_counts = Counter(t['class_level'] for t in tasks)
print('By grade:')
for g in sorted(grade_counts.keys()):
    print(f'  Grade {g}: {grade_counts[g]}')

# Save to file
output_file = 'data/movement_tasks_all.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(tasks, f, ensure_ascii=False, indent=2)

print(f'\nSaved to {output_file}')
print(f'Total: {len(tasks)} tasks')
