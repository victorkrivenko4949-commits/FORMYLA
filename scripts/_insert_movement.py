#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Insert movement tasks from adaptive_full_db.json into PostgreSQL
via the /api/migrate/push endpoint.
"""
import sys, json, re, requests
sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = 'https://formyla-com.onrender.com'
SECRET = 'formyla-migrate-2026'
TOPIC = 'Задачи на движение'

MOVE_RE = re.compile(
    r'скорост|км/ч|м/с|навстречу|вдогонку|'
    r'движен|велосипедист|пешеход|мотоциклист|'
    r'катер|лодк|поезд|выехал|догнал',
    re.IGNORECASE
)

# 1. Load JSON and find movement tasks
print('Loading adaptive_full_db.json...', flush=True)
with open('data/adaptive_full_db.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

movement = []
for t in data:
    q = t.get('question', '')
    if len(MOVE_RE.findall(q)) >= 2:
        movement.append(t)

print(f'Found {len(movement)} movement tasks in JSON', flush=True)

# Grade distribution
by_grade = {}
for t in movement:
    g = t.get('grade', '?')
    by_grade[g] = by_grade.get(g, 0) + 1
print('By grade:', flush=True)
for g in sorted(by_grade.keys()):
    print(f'  Grade {g}: {by_grade[g]}', flush=True)

# 2. Convert to DB format and insert
# Map JSON level (1-6) to difficulty_level (1-3)
def map_difficulty(level):
    if level <= 2:
        return 1
    elif level <= 4:
        return 2
    else:
        return 3

rows = []
for t in movement:
    rows.append({
        'class_level': t.get('grade', 5),
        'difficulty_level': map_difficulty(t.get('level', 3)),
        'topic': TOPIC,
        'task_text': t.get('question', ''),
        'solution': t.get('explanation', ''),
        'criteria_1_point': '',
        'criteria_2_points': '',
        'correct_answer': str(t.get('answer', '')),
    })

print(f'\nPrepared {len(rows)} rows for insertion', flush=True)

# 3. Insert via API in batches
batch_size = 25
total_inserted = 0

for i in range(0, len(rows), batch_size):
    batch = rows[i:i+batch_size]
    payload = {
        'secret': SECRET,
        'table': 'adaptive_tasks',
        'rows': batch
    }
    try:
        resp = requests.post(f'{BASE_URL}/api/migrate/push', json=payload, timeout=120)
        if resp.status_code == 200:
            result = resp.json()
            inserted = result.get('inserted', 0) + result.get('updated', 0)
            total_inserted += inserted
            print(f'  Batch {i//batch_size + 1}: inserted={inserted} (total={total_inserted})', flush=True)
        else:
            print(f'  Batch {i//batch_size + 1} ERROR: {resp.status_code} - {resp.text[:200]}', flush=True)
    except Exception as e:
        print(f'  Batch {i//batch_size + 1} EXCEPTION: {e}', flush=True)

print(f'\nTotal inserted: {total_inserted}', flush=True)

# 4. Verify
try:
    resp = requests.get(f'{BASE_URL}/api/migrate/tables?secret={SECRET}', timeout=30)
    if resp.status_code == 200:
        tables = resp.json()
        print(f'Total adaptive_tasks in DB: {tables.get("adaptive_tasks", "?")}', flush=True)
except:
    pass

print('\nDone!', flush=True)
