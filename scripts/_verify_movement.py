#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify movement tasks in DB."""
import sys, psycopg2
sys.stdout.reconfigure(encoding='utf-8')

DB = (
    'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe'
    '@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com'
    '/formyla?sslmode=require'
)

print('Connecting...', flush=True)
conn = psycopg2.connect(DB, connect_timeout=30)
cur = conn.cursor()

cur.execute(
    "SELECT class_level, COUNT(*) FROM adaptive_tasks "
    "WHERE topic = 'Задачи на движение' "
    "GROUP BY class_level ORDER BY class_level"
)
print('Movement tasks by grade:', flush=True)
total = 0
for g, c in cur.fetchall():
    print(f'  Grade {g}: {c}', flush=True)
    total += c
print(f'  TOTAL: {total}', flush=True)

# Show 3 samples
cur.execute(
    "SELECT id, class_level, difficulty_level, LEFT(task_text, 150) "
    "FROM adaptive_tasks WHERE topic = 'Задачи на движение' "
    "ORDER BY class_level, id LIMIT 5"
)
print('\nSamples:', flush=True)
for row in cur.fetchall():
    print(f'  ID={row[0]} grade={row[1]} diff={row[2]}: {row[3]}', flush=True)

cur.close()
conn.close()
print('\nDone!', flush=True)
