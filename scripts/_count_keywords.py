#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Count movement keywords in DB task_text."""
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

keywords = [
    'скорост', 'км/ч', 'навстречу', 'велосипедист',
    'пешеход', 'выехал', 'движен', 'поезд'
]

for kw in keywords:
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text ~* %s", (kw,))
    cnt = cur.fetchone()[0]
    print(f'  "{kw}": {cnt}', flush=True)

# Show a sample task with "навстречу"
cur.execute(
    "SELECT id, class_level, topic, LEFT(task_text, 200) FROM adaptive_tasks "
    "WHERE task_text ~* 'навстречу' LIMIT 5"
)
print('\nSample "навстречу" tasks:', flush=True)
for row in cur.fetchall():
    print(f'  ID={row[0]} grade={row[1]} topic="{row[2]}"', flush=True)
    print(f'    {row[3]}', flush=True)

# Show a sample task from grade 5 "Натуральные числа"
cur.execute(
    "SELECT id, class_level, topic, LEFT(task_text, 200) FROM adaptive_tasks "
    "WHERE class_level = 5 AND topic = 'Натуральные числа и действия с ними' "
    "ORDER BY id LIMIT 3"
)
print('\nSample grade 5 "Натуральные числа" tasks:', flush=True)
for row in cur.fetchall():
    print(f'  ID={row[0]} grade={row[1]} topic="{row[2]}"', flush=True)
    print(f'    {row[3]}', flush=True)

cur.close()
conn.close()
print('\nDone!', flush=True)
