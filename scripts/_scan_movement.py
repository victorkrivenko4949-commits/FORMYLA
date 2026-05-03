#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scan DB for movement-related keywords and show samples."""
import sys
import psycopg2
sys.stdout.reconfigure(encoding='utf-8')

DB = (
    'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe'
    '@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com'
    '/formyla?sslmode=require'
)

print('Connecting...', flush=True)
conn = psycopg2.connect(DB, connect_timeout=30)
cur = conn.cursor()
print('Connected!', flush=True)

# Search for ANY movement keyword
keywords = [
    'скорост', 'км/ч', 'м/с', 'навстречу', 'вдогонку',
    'пункта', 'выехал', 'расстояни', 'путь',
    'течени', 'велосипедист', 'пешеход', 'мотоциклист',
    'катер', 'лодк', 'поезд', 'догнал', 'обгон',
    'движен', 'ехал', 'проехал', 'шёл', 'шел'
]

for kw in keywords:
    cur.execute(
        "SELECT COUNT(*) FROM adaptive_tasks WHERE task_text ~* %s",
        (kw,)
    )
    cnt = cur.fetchone()[0]
    if cnt > 0:
        print(f'  "{kw}": {cnt} tasks', flush=True)

# Show tasks with "скорост"
print('\n--- Sample tasks with "скорост" ---', flush=True)
cur.execute(
    "SELECT id, class_level, topic, LEFT(task_text, 200) FROM adaptive_tasks "
    "WHERE task_text ~* 'скорост' LIMIT 10"
)
for row in cur.fetchall():
    print(f'\nID={row[0]} grade={row[1]} topic="{row[2]}"', flush=True)
    print(f'  {row[3]}', flush=True)

# Show tasks with "движен"
print('\n--- Sample tasks with "движен" ---', flush=True)
cur.execute(
    "SELECT id, class_level, topic, LEFT(task_text, 200) FROM adaptive_tasks "
    "WHERE task_text ~* 'движен' LIMIT 10"
)
for row in cur.fetchall():
    print(f'\nID={row[0]} grade={row[1]} topic="{row[2]}"', flush=True)
    print(f'  {row[3]}', flush=True)

# Show tasks with "км/ч" or "м/с"
print('\n--- Sample tasks with "км/ч" or "м/с" ---', flush=True)
cur.execute(
    "SELECT id, class_level, topic, LEFT(task_text, 200) FROM adaptive_tasks "
    "WHERE task_text ~* '(км/ч|м/с)' LIMIT 10"
)
for row in cur.fetchall():
    print(f'\nID={row[0]} grade={row[1]} topic="{row[2]}"', flush=True)
    print(f'  {row[3]}', flush=True)

# Show all distinct topics
print('\n--- All distinct topics ---', flush=True)
cur.execute("SELECT topic, COUNT(*) FROM adaptive_tasks GROUP BY topic ORDER BY COUNT(*) DESC")
for topic, cnt in cur.fetchall():
    print(f'  {topic}: {cnt}', flush=True)

cur.close()
conn.close()
print('\nDone!', flush=True)
