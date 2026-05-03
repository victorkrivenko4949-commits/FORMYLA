#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reclassify movement tasks via the Render API (no direct DB connection needed).
Uses the /api/migrate/push endpoint to update tasks.
"""
import sys, re, json, requests
sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = 'https://formyla-com.onrender.com'
SECRET = 'formyla-migrate-2026'

MOVEMENT_RE = re.compile(
    r'скорост|км/ч|м/с|навстречу|вдогонку|'
    r'из\s+пункта|из\s+города|выехал|'
    r'расстояни\w+\s+между|весь\s+путь|'
    r'по\s+течени|против\s+течени|собственн\w+\s+скорост|'
    r'велосипедист|пешеход|мотоциклист|катер|лодк|'
    r'поезд\w*\s+выех|догнал|обгон',
    re.IGNORECASE
)

NEW_TOPIC = 'Задачи на движение'

# Step 1: Export all tasks from the DB via API
print('Step 1: Fetching tasks from Render DB via API...')
all_tasks = []
offset = 0
limit = 500

while True:
    url = f'{BASE_URL}/api/migrate/export?secret={SECRET}&table=adaptive_tasks&offset={offset}&limit={limit}'
    print(f'  Fetching offset={offset}...')
    resp = requests.get(url, timeout=60)
    if resp.status_code != 200:
        print(f'  ERROR: {resp.status_code} - {resp.text[:200]}')
        break
    data = resp.json()
    rows = data.get('rows', [])
    if not rows:
        break
    all_tasks.extend(rows)
    offset += limit
    if len(rows) < limit:
        break

print(f'  Total tasks fetched: {len(all_tasks)}')

# Step 2: Find movement tasks
print('\nStep 2: Scanning for movement tasks...')
to_update = []
for task in all_tasks:
    text = task.get('task_text', '') or ''
    topic = task.get('topic', '') or ''
    if topic == NEW_TOPIC:
        continue  # already classified
    matches = MOVEMENT_RE.findall(text)
    if len(matches) >= 2:
        to_update.append(task)

print(f'  Found {len(to_update)} movement tasks to reclassify')

# Stats
by_grade = {}
for t in to_update:
    g = t.get('class_level', '?')
    by_grade[g] = by_grade.get(g, 0) + 1
print('\n  By grade:')
for g in sorted(by_grade.keys()):
    print(f'    Grade {g}: {by_grade[g]}')

by_topic = {}
for t in to_update:
    tp = t.get('topic', '?')
    by_topic[tp] = by_topic.get(tp, 0) + 1
print('\n  By old topic:')
for tp, c in sorted(by_topic.items(), key=lambda x: -x[1]):
    print(f'    {tp}: {c}')

# Step 3: Show sample tasks
if to_update:
    print('\n  Sample movement tasks:')
    for t in to_update[:5]:
        text = (t.get('task_text', '') or '')[:120]
        print(f'    ID={t["id"]} grade={t["class_level"]} old_topic="{t["topic"]}"')
        print(f'      {text}...')

# Step 4: Update via push API
if to_update:
    print(f'\nStep 3: Updating {len(to_update)} tasks via API...')
    
    # Prepare rows with only id and topic (the push endpoint does upsert)
    update_rows = []
    for t in to_update:
        update_rows.append({
            'id': t['id'],
            'class_level': t['class_level'],
            'difficulty_level': t['difficulty_level'],
            'topic': NEW_TOPIC,
            'task_text': t['task_text'],
            'solution': t.get('solution', ''),
            'criteria_1_point': t.get('criteria_1_point', ''),
            'criteria_2_points': t.get('criteria_2_points', ''),
            'correct_answer': t.get('correct_answer', ''),
        })
    
    # Send in batches of 50
    batch_size = 50
    updated = 0
    for i in range(0, len(update_rows), batch_size):
        batch = update_rows[i:i+batch_size]
        payload = {
            'secret': SECRET,
            'table': 'adaptive_tasks',
            'rows': batch
        }
        resp = requests.post(f'{BASE_URL}/api/migrate/push', json=payload, timeout=120)
        if resp.status_code == 200:
            result = resp.json()
            updated += result.get('inserted', 0) + result.get('updated', 0)
            print(f'  Batch {i//batch_size + 1}: {resp.json()}')
        else:
            print(f'  Batch {i//batch_size + 1} ERROR: {resp.status_code} - {resp.text[:200]}')
    
    print(f'\n  Total updated: {updated}')
else:
    print('\nNo tasks to update.')

print('\nDone!')
