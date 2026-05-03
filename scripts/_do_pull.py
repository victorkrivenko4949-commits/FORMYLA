#!/usr/bin/env python3
"""Quick pull: Render PG -> local SQLite adaptive_tasks table.

IMPORTANT: Stop the local Flask app first (it locks the SQLite DB).

Usage:
    python scripts/_do_pull.py
"""
import psycopg2
import sqlite3
import os
import sys

PG_URL = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'
LOCAL_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'formyla.db')
TABLE = 'adaptive_tasks'

print(f'Local DB: {LOCAL_DB}')

# Step 1: Connect to PostgreSQL
print('[1/4] Connecting to PostgreSQL...')
try:
    pg = psycopg2.connect(PG_URL, connect_timeout=15)
    cur = pg.cursor()
    print('  Connected!')
except Exception as e:
    print(f'  FAIL: {e}')
    sys.exit(1)

# Step 2: Get columns and data
print(f'[2/4] Fetching data from {TABLE}...')
cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{TABLE}' ORDER BY ordinal_position")
columns = [r[0] for r in cur.fetchall()]
print(f'  Columns ({len(columns)}): {columns}')

cur.execute(f'SELECT * FROM {TABLE} ORDER BY id')
rows = cur.fetchall()
print(f'  Fetched {len(rows)} rows')
pg.close()

# Step 3: Insert into SQLite
print(f'[3/4] Inserting into local SQLite ({TABLE})...')
try:
    sq = sqlite3.connect(LOCAL_DB, timeout=10)
except Exception as e:
    print(f'  FAIL connecting to SQLite: {e}')
    print('  Make sure the Flask app is stopped!')
    sys.exit(1)

# Check if table exists, drop it
existing_tables = [t[0] for t in sq.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f'  Existing tables: {existing_tables}')

if TABLE in existing_tables:
    sq.execute(f'DROP TABLE {TABLE}')
    print(f'  Dropped existing {TABLE}')

# Create table with same columns as PG (all TEXT for simplicity)
col_defs = []
for c in columns:
    if c == 'id':
        col_defs.append('id INTEGER PRIMARY KEY')
    elif c in ('class_level', 'difficulty_level', 'reports_count', 'attempts_count', 'solves_count', 'suggested_level'):
        col_defs.append(f'{c} INTEGER')
    elif c in ('is_flagged', 'is_active', 'needs_reclassification'):
        col_defs.append(f'{c} BOOLEAN DEFAULT 0')
    elif c in ('actual_solve_rate',):
        col_defs.append(f'{c} REAL')
    elif c in ('created_at', 'last_calibrated_at'):
        col_defs.append(f'{c} TIMESTAMP')
    else:
        col_defs.append(f'{c} TEXT')

create_sql = f'CREATE TABLE {TABLE} ({", ".join(col_defs)})'
sq.execute(create_sql)
sq.commit()
print(f'  Created table {TABLE}')

# Insert rows
placeholders = ', '.join(['?' for _ in columns])
col_names = ', '.join(columns)
errors = 0

for i, row in enumerate(rows):
    vals = []
    for v in row:
        if hasattr(v, 'isoformat'):
            vals.append(v.isoformat())
        elif isinstance(v, bool):
            vals.append(1 if v else 0)
        elif v is None:
            vals.append(None)
        else:
            vals.append(v)
    try:
        sq.execute(f'INSERT INTO {TABLE} ({col_names}) VALUES ({placeholders})', vals)
    except Exception as e:
        errors += 1
        if errors <= 3:
            print(f'  Row {i} error: {e}')
    if (i + 1) % 1000 == 0:
        sq.commit()
        print(f'  Inserted {i + 1}/{len(rows)}...')

sq.commit()

# Step 4: Verify
print(f'[4/4] Verifying...')
total = sq.execute(f'SELECT COUNT(*) FROM {TABLE}').fetchone()[0]
by_grade = sq.execute(f'SELECT class_level, COUNT(*) FROM {TABLE} GROUP BY class_level ORDER BY class_level').fetchall()
sq.close()

print(f'  Total in local SQLite: {total}')
for g, c in by_grade:
    status = 'OK' if int(c) >= 1050 else 'LOW'
    print(f'  Grade {g}: {c} {status}')

if errors > 0:
    print(f'  ({errors} rows had errors)')

print(f'\nDONE! Restart Flask app to see tasks locally.')
