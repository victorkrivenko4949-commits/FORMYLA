#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reclassify movement tasks using server-side SQL regex (no data transfer)."""
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
print('Connected!', flush=True)

# Check current state
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE topic = %s", (TOPIC,))
print(f'Already movement: {cur.fetchone()[0]}', flush=True)

# Server-side UPDATE using PostgreSQL regex (~*)
# Requires at least 2 movement indicators in task_text
SQL = """
UPDATE adaptive_tasks
SET topic = %s
WHERE topic != %s
  AND (
    (task_text ~* 'скорост' AND task_text ~* '(км/ч|м/с|навстречу|вдогонку|выехал|пешеход|велосипедист|катер|лодк|поезд|расстояни|путь)')
    OR (task_text ~* '(км/ч|м/с)' AND task_text ~* '(навстречу|вдогонку|выехал|расстояни|путь|пешеход|велосипедист)')
    OR (task_text ~* 'навстречу' AND task_text ~* '(выехал|скорост|расстояни)')
    OR (task_text ~* 'из пункта' AND task_text ~* '(скорост|выехал|навстречу)')
    OR (task_text ~* 'по течени' AND task_text ~* '(скорост|катер|лодк)')
    OR (task_text ~* 'против течени' AND task_text ~* '(скорост|катер|лодк)')
    OR (task_text ~* 'велосипедист' AND task_text ~* '(скорост|выехал|расстояни|догнал)')
    OR (task_text ~* 'пешеход' AND task_text ~* '(скорост|выехал|расстояни|навстречу)')
    OR (task_text ~* 'мотоциклист' AND task_text ~* '(скорост|выехал|расстояни|догнал)')
  )
"""

print('Running UPDATE...', flush=True)
cur.execute(SQL, (TOPIC, TOPIC))
updated = cur.rowcount
print(f'Updated: {updated} rows', flush=True)

conn.commit()
print('Committed!', flush=True)

# Verify
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

cur.close()
conn.close()
print('\nDone!', flush=True)
