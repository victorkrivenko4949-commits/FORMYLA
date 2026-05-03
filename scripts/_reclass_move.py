#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reclassify movement tasks in PostgreSQL - robust version."""
import sys, re, psycopg2
sys.stdout.reconfigure(encoding='utf-8')

DB = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'

MOVE_RE = re.compile(
    r'скорост|км/ч|м/с|навстречу|вдогонку|'
    r'из\s+пункта|из\s+города|выехал|'
    r'расстояни\w+\s+между|весь\s+путь|'
    r'по\s+течени|против\s+течени|собственн\w+\s+скорост|'
    r'велосипедист|пешеход|мотоциклист|катер|лодк|'
    r'поезд\w*\s+выех|догнал|обгон',
    re.IGNORECASE
)

TOPIC = 'Задачи на движение'

print('Connecting to Render PostgreSQL...', flush=True)
conn = psycopg2.connect(DB, connect_timeout=30)
conn.autocommit = False
cur = conn.cursor()
print('Connected!', flush=True)

# Count
cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
total = cur.fetchone()[0]
print(f'Total tasks: {total}', flush=True)

cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE topic = %s", (TOPIC,))
already = cur.fetchone()[0]
print(f'Already "{TOPIC}": {already}', flush=True)

# Fetch in batches to avoid timeout
print('Fetching tasks...', flush=True)
cur.execute(
    "SELECT id, class_level, topic, task_text FROM adaptive_tasks WHERE topic != %s ORDER BY id",
    (TOPIC,)
)

to_update = []
scanned = 0
for row in cur:
    task_id, grade, topic, text = row
    scanned += 1
    if not text:
        continue
    matches = MOVE_RE.findall(text)
    if len(matches) >= 2:
        to_update.append((task_id, grade, topic))

print(f'Scanned: {scanned}, found movement: {len(to_update)}', flush=True)

# Stats
by_grade = {}
for _, g, _ in to_update:
    by_grade[g] = by_grade.get(g, 0) + 1
print('\nBy grade:', flush=True)
for g in sorted(by_grade.keys()):
    print(f'  Grade {g}: {by_grade[g]}', flush=True)

by_topic = {}
for _, _, t in to_update:
    by_topic[t] = by_topic.get(t, 0) + 1
print('\nBy old topic:', flush=True)
for t, c in sorted(by_topic.items(), key=lambda x: -x[1]):
    print(f'  {t}: {c}', flush=True)

# Update
if to_update:
    ids = [t[0] for t in to_update]
    cur.execute(
        "UPDATE adaptive_tasks SET topic = %s WHERE id = ANY(%s)",
        (TOPIC, ids)
    )
    print(f'\nUpdated {cur.rowcount} rows', flush=True)
    conn.commit()
    print('Committed!', flush=True)

    # Verify
    cur.execute(
        "SELECT class_level, COUNT(*) FROM adaptive_tasks WHERE topic = %s GROUP BY class_level ORDER BY class_level",
        (TOPIC,)
    )
    print('\nFinal movement tasks by grade:', flush=True)
    tot = 0
    for g, c in cur.fetchall():
        print(f'  Grade {g}: {c}', flush=True)
        tot += c
    print(f'  TOTAL: {tot}', flush=True)

cur.close()
conn.close()
print('\nDone!', flush=True)
