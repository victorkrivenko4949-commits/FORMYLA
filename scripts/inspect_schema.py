# -*- coding: utf-8 -*-
import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('instance/formyla.db')
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print('ALL TABLES:', ', '.join(tables))

target = ['users', 'user_streaks', 'user_topic_progress', 'topic_mastery',
          'adaptive_test_results', 'adaptive_tests', 'adaptive_test_problems']

for t in target:
    if t in tables:
        cur.execute(f'PRAGMA table_info({t})')
        cols = cur.fetchall()
        cur.execute(f'SELECT COUNT(*) FROM {t}')
        cnt = cur.fetchone()[0]
        print(f'\n=== {t} ({cnt} rows) ===')
        for c in cols:
            nullable = 'NOT NULL' if c[3] else 'NULL'
            default = f' DEFAULT {c[4]}' if c[4] is not None else ''
            pk = ' PK' if c[5] else ''
            print(f'  {c[1]:30s} {c[2]:20s} {nullable}{default}{pk}')
    else:
        print(f'\n=== {t} -- NOT FOUND ===')

conn.close()
print('\nDONE')
