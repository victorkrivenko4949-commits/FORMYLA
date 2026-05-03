#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, re, psycopg2
sys.stdout.reconfigure(encoding='utf-8')

DB_URL = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'
DB_URL_EXT = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.oregon-postgres.render.com/formyla?sslmode=require'

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

print('Connecting...')
conn = psycopg2.connect(DB_URL, connect_timeout=20)
cur = conn.cursor()

# Current stats
cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
print(f'Total tasks: {cur.fetchone()[0]}')

cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE topic = %s", (NEW_TOPIC,))
print(f'Already movement: {cur.fetchone()[0]}')

# Fetch all non-movement tasks
cur.execute("SELECT id, class_level, topic, task_text FROM adaptive_tasks WHERE topic != %s", (NEW_TOPIC,))
rows = cur.fetchall()
print(f'Scanning {len(rows)} tasks...')

to_update = []
for task_id, grade, topic, text in rows:
    if not text:
        continue
    matches = MOVEMENT_RE.findall(text)
    if len(matches) >= 2:
        to_update.append((task_id, grade, topic))

print(f'\nFound {len(to_update)} movement tasks to reclassify')

by_grade = {}
for _, grade, _ in to_update:
    by_grade[grade] = by_grade.get(grade, 0) + 1
print('\nBy grade:')
for g in sorted(by_grade.keys()):
    print(f'  Grade {g}: {by_grade[g]}')

by_topic = {}
for _, _, topic in to_update:
    by_topic[topic] = by_topic.get(topic, 0) + 1
print('\nBy old topic:')
for tp, c in sorted(by_topic.items(), key=lambda x: -x[1]):
    print(f'  {tp}: {c}')

if to_update:
    ids = [t[0] for t in to_update]
    cur.execute("UPDATE adaptive_tasks SET topic = %s WHERE id = ANY(%s)", (NEW_TOPIC, ids))
    print(f'\nUpdated: {cur.rowcount} rows')
    conn.commit()

    # Verify
    cur.execute("SELECT class_level, COUNT(*) FROM adaptive_tasks WHERE topic = %s GROUP BY class_level ORDER BY class_level", (NEW_TOPIC,))
    print(f'\nFinal movement tasks by grade:')
    total = 0
    for g, c in cur.fetchall():
        print(f'  Grade {g}: {c}')
        total += c
    print(f'  Total: {total}')

conn.close()
print('\nDone!')
