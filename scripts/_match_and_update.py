#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Match movement tasks from adaptive_full_db.json to DB records by question text,
then update their topic to 'Задачи на движение'.
"""
import sys, json, re, psycopg2
sys.stdout.reconfigure(encoding='utf-8')

DB = (
    'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe'
    '@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com'
    '/formyla?sslmode=require'
)

TOPIC = 'Задачи на движение'

# Movement keyword pattern
MOVE_RE = re.compile(
    r'скорост|км/ч|м/с|навстречу|вдогонку|'
    r'движен|велосипедист|пешеход|мотоциклист|'
    r'катер|лодк|поезд|выехал|догнал',
    re.IGNORECASE
)

# 1. Find movement tasks in JSON
print('Loading adaptive_full_db.json...', flush=True)
with open('data/adaptive_full_db.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

movement_questions = []
for t in data:
    q = t.get('question', '')
    if len(MOVE_RE.findall(q)) >= 2:
        movement_questions.append(t)

print(f'Found {len(movement_questions)} movement tasks in JSON', flush=True)

# Show grade distribution
by_grade = {}
for t in movement_questions:
    g = t.get('grade', '?')
    by_grade[g] = by_grade.get(g, 0) + 1
print('By grade in JSON:', flush=True)
for g in sorted(by_grade.keys()):
    print(f'  Grade {g}: {by_grade[g]}', flush=True)

# 2. Connect to DB and find matching tasks
print('\nConnecting to DB...', flush=True)
conn = psycopg2.connect(DB, connect_timeout=30)
cur = conn.cursor()

# For each movement task, find it in DB by matching first 50 chars of question
# (stripping LaTeX)
def normalize(text):
    """Strip LaTeX and whitespace for matching."""
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    text = re.sub(r'[\\${}()\[\]]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:80].lower()

# Build lookup from JSON questions
json_normalized = {}
for t in movement_questions:
    key = normalize(t['question'])
    json_normalized[key] = t

print(f'Unique normalized keys: {len(json_normalized)}', flush=True)

# Now do a broad SQL update using PostgreSQL regex
# Use the same pattern as the content-based fallback in app.py
SQL_UPDATE = """
UPDATE adaptive_tasks
SET topic = %s
WHERE topic != %s
  AND (
    task_text ~* 'скорост' 
    OR task_text ~* 'км/ч'
    OR task_text ~* 'м/с'
    OR task_text ~* 'навстречу'
    OR task_text ~* 'вдогонку'
    OR task_text ~* 'велосипедист'
    OR task_text ~* 'пешеход'
  )
  AND (
    task_text ~* 'скорост'
    OR task_text ~* 'км/ч'
    OR task_text ~* 'м/с'
  )
"""

print('Running UPDATE...', flush=True)
cur.execute(SQL_UPDATE, (TOPIC, TOPIC))
updated = cur.rowcount
print(f'Updated: {updated} rows', flush=True)
conn.commit()
print('Committed!', flush=True)

# 3. Verify
cur.execute(
    "SELECT class_level, COUNT(*) FROM adaptive_tasks "
    "WHERE topic = %s GROUP BY class_level ORDER BY class_level",
    (TOPIC,)
)
print('\nMovement tasks by grade:', flush=True)
total = 0
for g, c in cur.fetchall():
    print(f'  Grade {g}: {c}', flush=True)
    total += c
print(f'  TOTAL: {total}', flush=True)

# 4. Show samples
cur.execute(
    "SELECT id, class_level, LEFT(task_text, 120) FROM adaptive_tasks "
    "WHERE topic = %s ORDER BY class_level, id LIMIT 15",
    (TOPIC,)
)
print('\nSample movement tasks:', flush=True)
for row in cur.fetchall():
    print(f'  ID={row[0]} grade={row[1]}: {row[2]}', flush=True)

cur.close()
conn.close()
print('\nDone!', flush=True)
