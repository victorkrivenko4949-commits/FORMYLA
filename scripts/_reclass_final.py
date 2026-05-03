#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Final reclassification - single connection, single query."""
import sys
import psycopg2
sys.stdout.reconfigure(encoding='utf-8')

DB = (
    'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe'
    '@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com'
    '/formyla?sslmode=require'
)

TOPIC = 'Задачи на движение'

print('Connecting...', flush=True)
conn = psycopg2.connect(DB, connect_timeout=30)
cur = conn.cursor()

# 1. Check what we already have
cur.execute("SELECT id, class_level, LEFT(task_text, 150) FROM adaptive_tasks WHERE topic = %s", (TOPIC,))
existing = cur.fetchall()
print(f'Already "{TOPIC}": {len(existing)}', flush=True)
for row in existing:
    print(f'  ID={row[0]} grade={row[1]}: {row[2]}', flush=True)

# 2. Broader UPDATE - any task with at least ONE strong movement keyword
SQL = """
UPDATE adaptive_tasks
SET topic = %s
WHERE topic != %s
  AND (
    task_text ~* '(км/ч|м/с|навстречу|вдогонку)'
    OR (task_text ~* 'скорост' AND task_text ~* '(движен|ехал|шел|шёл|пешеход|велосипед|поезд|катер|лодк|расстояни|пункт|город)')
    OR (task_text ~* 'из пункта' AND task_text ~* '(скорост|ехал|движен)')
    OR (task_text ~* 'по течени|против течени')
    OR (task_text ~* 'движен' AND task_text ~* '(скорост|ехал|пешеход|велосипед|поезд)')
  )
"""
cur.execute(SQL, (TOPIC, TOPIC))
updated = cur.rowcount
print(f'\nNewly updated: {updated} rows', flush=True)
conn.commit()

# 3. Show all movement tasks now
cur.execute(
    "SELECT id, class_level, LEFT(task_text, 150) FROM adaptive_tasks WHERE topic = %s ORDER BY class_level, id",
    (TOPIC,)
)
rows = cur.fetchall()
print(f'\nTotal movement tasks: {len(rows)}', flush=True)
for row in rows:
    print(f'  ID={row[0]} grade={row[1]}: {row[2]}', flush=True)

# 4. Show all topics with counts
cur.execute("SELECT topic, COUNT(*) FROM adaptive_tasks GROUP BY topic ORDER BY COUNT(*) DESC")
print('\nAll topics:', flush=True)
for topic, cnt in cur.fetchall():
    print(f'  {topic}: {cnt}', flush=True)

cur.close()
conn.close()
print('\nDone!', flush=True)
