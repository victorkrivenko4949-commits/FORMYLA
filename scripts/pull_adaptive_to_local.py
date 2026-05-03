#!/usr/bin/env python3
"""Pull adaptive_tasks from Render PostgreSQL into local SQLite.

Approach: Uses the production app's /api/migrate/export endpoint.
If that's not available, falls back to direct PostgreSQL connection attempt.

Usage:
    python scripts/pull_adaptive_to_local.py
"""

import os
import sys
import json
import sqlite3
import requests
import time

RENDER_URL = 'https://formyla-com.onrender.com'
MIGRATE_SECRET = 'formyla-migrate-2026'
LOCAL_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'formyla.db')
BATCH_SIZE = 500
TABLE = 'adaptive_tasks'  # plural on Render


def create_table(conn):
    """Create adaptive_task table in SQLite if it doesn't exist."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS adaptive_task (
            id INTEGER PRIMARY KEY,
            grade INTEGER NOT NULL,
            topic VARCHAR(100),
            difficulty INTEGER,
            task_text TEXT NOT NULL,
            correct_answer VARCHAR(500),
            solution TEXT,
            task_type VARCHAR(50) DEFAULT 'short_answer',
            answer_type VARCHAR(50) DEFAULT 'text',
            options TEXT,
            is_active INTEGER DEFAULT 1,
            is_flagged INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            subtopic VARCHAR(200),
            attempts_count INTEGER DEFAULT 0,
            solves_count INTEGER DEFAULT 0,
            actual_solve_rate REAL,
            suggested_level INTEGER,
            needs_reclassification INTEGER DEFAULT 0,
            last_calibrated_at TIMESTAMP
        )
    ''')
    conn.commit()


def try_export_endpoint():
    """Try the /api/migrate/export endpoint."""
    url = f'{RENDER_URL}/api/migrate/export'
    try:
        r = requests.get(url, params={
            'secret': MIGRATE_SECRET,
            'table': TABLE,
            'offset': 0, 'limit': 1
        }, timeout=30)
        if r.status_code == 200:
            return True
    except:
        pass
    return False


def pull_via_export(offset, limit):
    """Pull batch via export endpoint."""
    url = f'{RENDER_URL}/api/migrate/export'
    r = requests.get(url, params={
        'secret': MIGRATE_SECRET,
        'table': TABLE,
        'offset': offset,
        'limit': limit
    }, timeout=60)
    if r.status_code == 200:
        return r.json()
    return None


def pull_via_psycopg():
    """Pull all rows via direct PostgreSQL connection."""
    print('[INFO] Trying direct PostgreSQL connection...')
    
    # Read connection string
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env.migration')
    db_url = None
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith('EXTERNAL_DATABASE_URL='):
                    db_url = line.split('=', 1)[1].strip()
    
    if not db_url:
        print('[FAIL] No EXTERNAL_DATABASE_URL found in .env.migration')
        return None
    
    try:
        import psycopg2
    except ImportError:
        print('[FAIL] psycopg2 not installed. Run: pip install psycopg2-binary')
        return None
    
    try:
        print(f'  Connecting to PostgreSQL (timeout 15s)...')
        conn = psycopg2.connect(db_url, connect_timeout=15)
        cur = conn.cursor()
        
        # Get column names
        cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{TABLE}' ORDER BY ordinal_position")
        columns = [r[0] for r in cur.fetchall()]
        print(f'  Columns: {columns}')
        
        # Get all rows
        cur.execute(f'SELECT * FROM {TABLE} ORDER BY id')
        rows_raw = cur.fetchall()
        print(f'  Fetched {len(rows_raw)} rows')
        
        rows = []
        for r in rows_raw:
            row_dict = {}
            for i, col in enumerate(columns):
                val = r[i]
                if hasattr(val, 'isoformat'):
                    val = val.isoformat()
                row_dict[col] = val
            rows.append(row_dict)
        
        conn.close()
        return {'columns': columns, 'rows': rows, 'total': len(rows)}
    except Exception as e:
        print(f'  [FAIL] PostgreSQL connection failed: {e}')
        return None


def insert_rows(conn, rows, columns):
    """Insert rows into local SQLite."""
    # Map PG column names to SQLite column names
    # PG table is 'adaptive_tasks', SQLite model is 'adaptive_task'
    inserted = 0
    for row in rows:
        cols = [c for c in columns if row.get(c) is not None]
        placeholders = ', '.join(['?' for _ in cols])
        col_names = ', '.join(cols)
        values = [row.get(c) for c in cols]
        try:
            conn.execute(
                f'INSERT OR REPLACE INTO adaptive_task ({col_names}) VALUES ({placeholders})',
                values
            )
            inserted += 1
        except Exception as e:
            print(f'  [WARN] Row {row.get("id")}: {e}')
        
        if inserted % 500 == 0 and inserted > 0:
            conn.commit()
            print(f'  Inserted {inserted}/{len(rows)}...')
    
    conn.commit()
    return inserted


def main():
    print('=' * 60)
    print('Pull adaptive_tasks from Render to local SQLite')
    print('=' * 60)
    print(f'Render: {RENDER_URL}')
    print(f'Local DB: {LOCAL_DB}')
    print()

    # Try export endpoint first
    print('[1] Checking /api/migrate/export endpoint...')
    if try_export_endpoint():
        print('  Export endpoint available!')
        
        # Get total
        data = pull_via_export(0, 1)
        total = data['total']
        columns = data['columns']
        print(f'  Total rows: {total}')
        
        # Pull all
        print(f'\n[2] Pulling {total} rows in batches of {BATCH_SIZE}...')
        all_rows = []
        offset = 0
        while offset < total:
            batch = pull_via_export(offset, BATCH_SIZE)
            if batch is None:
                print(f'  [FAIL] Batch at offset {offset} failed')
                sys.exit(1)
            all_rows.extend(batch['rows'])
            print(f'  {len(all_rows)}/{total}')
            offset += BATCH_SIZE
            time.sleep(0.3)
    else:
        print('  Export endpoint not available, trying direct PG...')
        result = pull_via_psycopg()
        if result is None:
            print('\n[FAIL] Cannot pull data. Options:')
            print('  1. Wait for Render to deploy the export endpoint')
            print('  2. Install psycopg2-binary and ensure PG is accessible')
            sys.exit(1)
        all_rows = result['rows']
        columns = result['columns']
        total = result['total']
    
    print(f'\n[3] Inserting {len(all_rows)} rows into local SQLite...')
    conn = sqlite3.connect(LOCAL_DB)
    create_table(conn)
    
    # Clear existing
    existing = conn.execute('SELECT COUNT(*) FROM adaptive_task').fetchone()[0]
    if existing > 0:
        print(f'  Clearing {existing} existing rows...')
        conn.execute('DELETE FROM adaptive_task')
        conn.commit()
    
    inserted = insert_rows(conn, all_rows, columns)
    conn.close()
    print(f'  Inserted {inserted} rows')
    
    # Verify
    print(f'\n[4] Verifying...')
    conn = sqlite3.connect(LOCAL_DB)
    total_local = conn.execute('SELECT COUNT(*) FROM adaptive_task').fetchone()[0]
    by_grade = conn.execute(
        'SELECT grade, COUNT(*) FROM adaptive_task GROUP BY grade ORDER BY grade'
    ).fetchall()
    conn.close()
    
    print(f'  Total in local DB: {total_local}')
    for grade, count in by_grade:
        s = 'OK' if count >= 1050 else 'LOW'
        print(f'    Grade {grade}: {count} {s}')
    
    print(f'\n=== DONE! Restart Flask to see tasks locally. ===')


if __name__ == '__main__':
    main()
