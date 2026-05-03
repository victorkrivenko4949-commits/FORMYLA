#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick status check for adaptive test tasks."""
import psycopg2, json, os

DB_URL = ('postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe'
          '@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com'
          '/formyla?sslmode=require')

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

# Overall counts
cur.execute('SELECT class_level, COUNT(*) FROM adaptive_tasks GROUP BY class_level ORDER BY class_level')
rows = cur.fetchall()
print('=== ADAPTIVE TEST TASK COUNTS ===')
print(f'{"Grade":>5} | {"Count":>6} | {"Target":>6} | {"Status"}')
print('-' * 40)
total = 0
for grade, count in rows:
    target = 1050
    status = 'DONE' if count >= target else f'need {target - count} more'
    print(f'{grade:>5} | {count:>6} | {target:>6} | {status}')
    total += count
print(f'{"TOTAL":>5} | {total:>6}')

# Check generation progress files
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for g in [5, 6, 7, 8, 9, 10]:
    cp = os.path.join(BASE, 'data', 'audit', f'gen_progress_grade{g}.json')
    if os.path.exists(cp):
        data = json.load(open(cp, encoding='utf-8'))
        total_gen = sum(data.values())
        print(f'\nGrade {g} checkpoint: {total_gen} tasks generated, {len(data)} topic-levels')

conn.close()
