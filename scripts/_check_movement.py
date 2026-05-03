#!/usr/bin/env python3
import psycopg2, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PG_URL = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'
conn = psycopg2.connect(PG_URL, connect_timeout=15)
cur = conn.cursor()

# Check movement tasks content for each grade
for grade in range(5, 12):
    cur.execute("""SELECT id, LEFT(task_text, 150) FROM adaptive_tasks 
        WHERE class_level=%s AND topic='Задачи на движение' 
        ORDER BY id DESC LIMIT 3""", (grade,))
    rows = cur.fetchall()
    print(f'=== Grade {grade} ({len(rows)} shown) ===')
    for r in rows:
        print(f'  ID {r[0]}: {r[1][:120]}...')
    print()

# Also check: are there tasks with topic containing 'движен' but NOT exactly 'Задачи на движение'?
cur.execute("""SELECT DISTINCT topic FROM adaptive_tasks WHERE topic ILIKE '%%движен%%'""")
print('All topics containing "движен":')
for r in cur.fetchall():
    print(f'  [{r[0]}]')

conn.close()
