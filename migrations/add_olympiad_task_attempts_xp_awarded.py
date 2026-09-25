#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration: add the `xp_awarded` column to `olympiad_task_attempts`.

XP_AWARD_V1 (25.09.2026): роут /olympiads/task/<id>/submit раньше возвращал
xp_earned=10 в JSON, но не начислял ни рейтинга (users.experience_points),
ни счётчика решённых (users.total_problems_solved). Решённые олимпиадные
задачи не попадали в статистику «решено» и в лидерборд.

Колонка xp_awarded (BOOLEAN NOT NULL DEFAULT FALSE) нужна, чтобы:
  - начислять +10 XP и +1 решённую только за первое решение задачи;
  - доначислить XP за уже решённые задачи (backfill при старте приложения).

Idempotent: safely skips if the column already exists.

Usage:
    # Local SQLite
    python migrations/add_olympiad_task_attempts_xp_awarded.py

    # Production PostgreSQL (uses DATABASE_URL from env)
    python migrations/add_olympiad_task_attempts_xp_awarded.py --pg
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

TABLE = 'olympiad_task_attempts'
COLUMN = 'xp_awarded'


# ── SQLite path ───────────────────────────────────────────────────────────────

def _sqlite_column_exists(conn: Any, table: str, column: str) -> bool:
    cur = conn.execute(f'PRAGMA table_info({table})')
    return any(row[1] == column for row in cur.fetchall())


def migrate_sqlite() -> None:
    import sqlite3

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    instance_db = os.path.join(project_root, 'instance', 'formyla.db')
    root_db = os.path.join(project_root, 'formyla.db')
    db_path = instance_db if os.path.exists(instance_db) else root_db

    if not os.path.exists(db_path):
        print(f'[!] SQLite DB not found at {db_path} — skipping.')
        return

    print(f' SQLite migration: adding {TABLE}.{COLUMN} …')
    conn = sqlite3.connect(db_path)
    try:
        if _sqlite_column_exists(conn, TABLE, COLUMN):
            print(f'[OK] {TABLE}.{COLUMN} already exists — skipped.')
            return

        conn.execute(
            f'ALTER TABLE {TABLE} ADD COLUMN {COLUMN} '
            f"BOOLEAN NOT NULL DEFAULT 0"
        )
        conn.commit()
        print(f'[OK] Column {TABLE}.{COLUMN} added successfully.')
    except Exception as e:
        conn.rollback()
        print(f'[ERROR] Error: {e}', file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


# ── PostgreSQL path ────────────────────────────────────────────────────────────

def migrate_postgres(dsn: str) -> None:
    try:
        import psycopg  # psycopg 3.x
    except ImportError:
        print('[ERROR] psycopg not installed. pip install "psycopg[binary]"', file=sys.stderr)
        sys.exit(1)

    print(f' PostgreSQL migration: adding {TABLE}.{COLUMN} …')

    with psycopg.connect(dsn, autocommit=False) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = %s AND column_name = %s",
                    (TABLE, COLUMN),
                )
                if cur.fetchone():
                    print(f'[OK] {TABLE}.{COLUMN} already exists — skipped.')
                    return

                cur.execute(
                    f'ALTER TABLE {TABLE} ADD COLUMN {COLUMN} '
                    f'BOOLEAN NOT NULL DEFAULT FALSE'
                )
            conn.commit()
            print(f'[OK] Column {TABLE}.{COLUMN} added successfully.')
        except Exception as e:
            conn.rollback()
            print(f'[ERROR] Error: {e}', file=sys.stderr)
            sys.exit(1)


# ── main ──────────────────────────────────────────────────────────────────────

def ensure_column_sqla() -> None:
    """Runtime helper для app.py: добавляет колонку, если её нет (SQLite/PG).

    Использует уже подключённый SQLAlchemy engine приложения, поэтому работает
    и для SQLite, и для PostgreSQL без отдельного запуска миграции руками.
    """
    from models import db

    inspector = db.inspect(db.engine)
    if COLUMN not in [c['name'] for c in inspector.get_columns(TABLE)]:
        with db.engine.begin() as conn:
            dialect = conn.dialect.name
            if dialect == 'postgresql':
                conn.execute(
                    db.text(f'ALTER TABLE {TABLE} ADD COLUMN {COLUMN} '
                            f'BOOLEAN NOT NULL DEFAULT FALSE')
                )
            else:
                conn.execute(
                    db.text(f'ALTER TABLE {TABLE} ADD COLUMN {COLUMN} '
                            f'BOOLEAN NOT NULL DEFAULT 0')
                )
        print(f'[OK] Column {TABLE}.{COLUMN} added (runtime ensure).')


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
            print('[ERROR] Need DSN: --pg postgres://... or DATABASE_URL env var.',
                  file=sys.stderr)
            sys.exit(1)
        migrate_postgres(dsn)
    else:
        migrate_sqlite()

    print('\n[OK] Migration complete.')


if __name__ == '__main__':
    main()
