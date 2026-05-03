#!/usr/bin/env python3
"""Export movement tasks via Render HTTP API."""
import requests, json, sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

RENDER_URL = 'https://formyla-com.onrender.com'
SECRET = 'formyla-migrate-2026'

all_tasks = []
offset = 0
batch = 200

while True:
    print(f'Fetching offset {offset}...')
    r = requests.get(f'{RENDER_URL}/api/migrate/export', params={
        'secret': SECRET,
        'table': 'adaptive_tasks',
        'offset': offset,
        'limit': batch
    }, timeout=60)
    
    if r.status_code != 200:
        print(f'Error: {r.status_code} - trying direct approach')
        break
    
    data = r.json()
    rows = data.get('rows', [])
    total = data.get('total', 0)
    
    # Filter movement tasks
    for row in rows:
        if row.get('topic') == 'Задачи на движение':
            all_tasks.append(row)
    
    print(f'  Got {len(rows)} rows, {len(all_tasks)} movement so far (total in DB: {total})')
    
    offset += batch
    if offset >= total:
        break
    time.sleep(0.5)

if not all_tasks:
    # Fallback: direct PG with timeout
    print('\nFallback: direct PG connection...')
    import psycopg2
    PG_URL = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'
    conn = psycopg2.connect(PG_URL, connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT id, class_level, difficulty_level, topic, task_text, correct_answer, solution FROM adaptive_tasks WHERE topic='Задачи на движение' ORDER BY class_level, id")
    cols = ['id', 'class_level', 'difficulty_level', 'topic', 'task_text', 'correct_answer', 'solution']
    for row in cur.fetchall():
        task = {}
        for i, c in enumerate(cols):
            v = row[i]
            if hasattr(v, 'isoformat'):
                v = v.isoformat()
            task[c] = v
        all_tasks.append(task)
    conn.close()

print(f'\nTotal movement tasks: {len(all_tasks)}')

# Count by grade
from collections import Counter
gc = Counter(t.get('class_level') for t in all_tasks)
for g in sorted(gc.keys()):
    print(f'  Grade {g}: {gc[g]}')

# Save
with open('data/movement_tasks_all.json', 'w', encoding='utf-8') as f:
    json.dump(all_tasks, f, ensure_ascii=False, indent=2)
print(f'\nSaved to data/movement_tasks_all.json ({len(all_tasks)} tasks)')
