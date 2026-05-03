#!/usr/bin/env python3
import psycopg2, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
PG_URL = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'
conn = psycopg2.connect(PG_URL, connect_timeout=15)
cur = conn.cursor()
for tid in [9599, 7136]:
    cur.execute('SELECT id, class_level, topic, LEFT(task_text, 120) FROM adaptive_tasks WHERE id=%s', (tid,))
    r = cur.fetchone()
    if r:
        print(f'ID {r[0]} | Grade {r[1]} | Topic: [{r[2]}]')
        print(f'  Text: {r[3]}')
        print()
conn.close()
