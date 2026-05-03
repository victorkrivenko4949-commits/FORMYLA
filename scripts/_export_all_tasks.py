#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export all adaptive tasks from PostgreSQL to a JSON file."""
import sys, json, requests
sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = 'https://formyla-com.onrender.com'
SECRET = 'formyla-migrate-2026'

# First check total count
resp = requests.get(f'{BASE_URL}/api/migrate/tables?secret={SECRET}', timeout=30)
tables = resp.json()
total = tables.get('adaptive_tasks', 0)
print(f'Total adaptive_tasks in DB: {total}', flush=True)

# The /api/migrate/export endpoint is not deployed yet.
# So we'll use direct psycopg2 connection to export.
import psycopg2

DB = (
    'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe'
    '@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com'
    '/formyla?sslmode=require'
)

print('Connecting to DB...', flush=True)
conn = psycopg2.connect(DB, connect_timeout=30)
cur = conn.cursor()

# Fetch all tasks
print('Fetching all tasks...', flush=True)
cur.execute("""
    SELECT id, class_level, difficulty_level, topic, task_text, 
           solution, criteria_1_point, criteria_2_points, correct_answer, is_flagged
    FROM adaptive_tasks 
    ORDER BY class_level, topic, id
""")

columns = ['id', 'class_level', 'difficulty_level', 'topic', 'task_text',
           'solution', 'criteria_1_point', 'criteria_2_points', 'correct_answer', 'is_flagged']

tasks = []
for row in cur.fetchall():
    task = {}
    for i, col in enumerate(columns):
        val = row[i]
        if val is None:
            val = '' if col != 'is_flagged' else False
        task[col] = val
    tasks.append(task)

print(f'Fetched {len(tasks)} tasks', flush=True)

# Stats
by_grade = {}
by_topic = {}
for t in tasks:
    g = t['class_level']
    tp = t['topic']
    by_grade[g] = by_grade.get(g, 0) + 1
    by_topic[tp] = by_topic.get(tp, 0) + 1

print('\nBy grade:', flush=True)
for g in sorted(by_grade.keys()):
    print(f'  Grade {g}: {by_grade[g]}', flush=True)

print(f'\nTotal topics: {len(by_topic)}', flush=True)

# Save to file
output_file = 'data/all_adaptive_tasks_export.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(tasks, f, ensure_ascii=False, indent=2)

print(f'\nSaved to {output_file}', flush=True)

cur.close()
conn.close()
print('Done!', flush=True)
