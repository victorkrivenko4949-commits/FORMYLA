#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration: add the missing `number` column to `olympiad_tasks`.

The column `olympiad_tasks.number` (VARCHAR(10), NOT NULL) exists in the
SQLAlchemy model (`models_olympiad.py:144`) but is missing from the actual
PostgreSQL table on the production server.  This happens because the initial
migration (`add_olympiad_section.py`) created the table before the `number`
column was added to the model, and no subsequent ALTER TABLE was ever run
against the production database.

Idempotent: safely skips if the column already exists.

Usage:
    # Local SQLite
    python migrations/add_olympiad_tasks_number_column.py

    # Production PostgreSQL (uses DATABASE_URL from env)
    python migrations/add_olympiad_tasks_number_column.py --pg
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from typing import Any

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


TABLE = 'olympiad_tasks'
COLUMN = 'number'


# ── SQLite path ───────────────────────────────────────────────────────────────

def _sqlite_column_exists(conn: Any, table: str, column: str) -> bool:
    cur = conn.execute(f'PRAGMA table_info({table})')
    return any(row[1] == column for row in cur.fetchall())


def migrate_sqlite() -> None:
    import sqlite3

    # Find the DB file — same logic as add_vsosh9_method_fields.py
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    instance_db = os.path.join(project_root, 'instance', 'formyla.db')
    root_db = os.path.join(project_root, 'formyla.db')
    db_path = instance_db if os.path.exists(instance_db) else root_db

    if not os.path.exists(db_path):
        print(f'⚠️  SQLite DB not found at {db_path} — skipping.')
        return

    print(f'🔄 SQLite migration: adding {TABLE}.{COLUMN} …')
    conn = sqlite3.connect(db_path)
    try:
        if _sqlite_column_exists(conn, TABLE, COLUMN):
            print(f'✅ {TABLE}.{COLUMN} already exists — skipped.')
            return

        conn.execute(f'ALTER TABLE {TABLE} ADD COLUMN {COLUMN} VARCHAR(10) NOT NULL DEFAULT \'\'')
        conn.commit()
        print(f'✅ Column {TABLE}.{COLUMN} added successfully.')
    except Exception as e:
        conn.rollback()
        print(f'❌ Error: {e}', file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


# ── PostgreSQL path ───────────────────────────────────────────────────────────

def migrate_postgres(dsn: str) -> None:
    try:
        import psycopg  # psycopg 3.x
    except ImportError:
        print('❌ psycopg not installed. pip install "psycopg[binary]"', file=sys.stderr)
        sys.exit(1)

    print(f'🔄 PostgreSQL migration: adding {TABLE}.{COLUMN} …')

    with psycopg.connect(dsn, autocommit=False) as conn:
        try:
            with conn.cursor() as cur:
                # Check if column already exists
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = %s AND column_name = %s",
                    (TABLE, COLUMN),
                )
                if cur.fetchone():
                    print(f'✅ {TABLE}.{COLUMN} already exists — skipped.')
                    return

                # Add the column.  Existing rows get '' as default.
                cur.execute(
                    f'ALTER TABLE {TABLE} ADD COLUMN {COLUMN} VARCHAR(10) NOT NULL DEFAULT \'\''
                )
            conn.commit()
            print(f'✅ Column {TABLE}.{COLUMN} added successfully.')
        except Exception as e:
            conn.rollback()
            print(f'❌ Error: {e}', file=sys.stderr)
            sys.exit(1)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        '--pg', nargs='?', const='', default=None,
        help='Use PostgreSQL. Without value — reads DATABASE_URL from env.',
    )
    args = parser.parse_args()

    if args.pg is not None:
        dsn = args.pg or os.environ.get('DATABASE_URL', '')
        if not dsn:
            print('❌ Need DSN: --pg postgres://... or DATABASE_URL env var.',
                  file=sys.stderr)
            sys.exit(1)
        migrate_postgres(dsn)
    else:
        migrate_sqlite()

    print('\n✅ Migration complete.')


if __name__ == '__main__':
    main()
