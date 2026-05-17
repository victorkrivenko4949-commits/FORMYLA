# -*- coding: utf-8 -*-
"""
Migration: add VsOSh-9 method-bank fields to olympiad_theory & olympiad_tasks.

Columns added (all nullable, safe defaults — никакие старые данные не
ломаются):

  olympiad_theory:
    total_count      INTEGER         — точное число задач ВсОШ-9 у метода.
    share_percent    REAL/DOUBLE     — доля 0..1 (например 0.1356).

  olympiad_tasks:
    method_codes     JSON/JSONB      — массив методов вида ["E14","F3"].
    year             INTEGER         — год тура (2010..2026).
    stage            VARCHAR(20)     — 'school' | 'municipal' | 'regional' | 'final'.

Идемпотентно: повторный запуск пропустит уже существующие колонки.
Поддерживает SQLite (по умолчанию) и PostgreSQL (с флагом --pg).

Usage:
    python migrations/add_vsosh9_method_fields.py            # SQLite (formyla.db)
    python migrations/add_vsosh9_method_fields.py --db PATH  # явный путь к sqlite БД
    python migrations/add_vsosh9_method_fields.py --pg DSN   # PostgreSQL по DSN
                                                            # или env DATABASE_URL
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
import sys
from datetime import datetime
from typing import Callable

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


# Колонки добавляются в следующем виде: (table, column, sqlite_sql, postgres_sql).
ADDITIONS = [
    ('olympiad_theory', 'total_count',
     'ALTER TABLE olympiad_theory ADD COLUMN total_count INTEGER',
     'ALTER TABLE olympiad_theory ADD COLUMN IF NOT EXISTS total_count INTEGER'),
    ('olympiad_theory', 'share_percent',
     'ALTER TABLE olympiad_theory ADD COLUMN share_percent REAL',
     'ALTER TABLE olympiad_theory ADD COLUMN IF NOT EXISTS share_percent DOUBLE PRECISION'),
    ('olympiad_tasks', 'method_codes',
     'ALTER TABLE olympiad_tasks ADD COLUMN method_codes JSON',
     'ALTER TABLE olympiad_tasks ADD COLUMN IF NOT EXISTS method_codes JSONB'),
    ('olympiad_tasks', 'year',
     'ALTER TABLE olympiad_tasks ADD COLUMN year INTEGER',
     'ALTER TABLE olympiad_tasks ADD COLUMN IF NOT EXISTS year INTEGER'),
    ('olympiad_tasks', 'stage',
     'ALTER TABLE olympiad_tasks ADD COLUMN stage VARCHAR(20)',
     'ALTER TABLE olympiad_tasks ADD COLUMN IF NOT EXISTS stage VARCHAR(20)'),
]


# ── SQLite path ───────────────────────────────────────────────────────────────

def _sqlite_column_exists(conn, table: str, column: str) -> bool:
    cur = conn.execute(f'PRAGMA table_info({table})')
    return any(row[1] == column for row in cur.fetchall())


def _sqlite_table_exists(conn, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cur.fetchone() is not None


def _sqlite_backup(db_path: str) -> str:
    backups_dir = os.path.join(os.path.dirname(db_path) or '.', 'backups')
    os.makedirs(backups_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(backups_dir, f'formyla_before_vsosh9_method_fields_{ts}.db')
    shutil.copy2(db_path, dst)
    print(f'✅ Бэкап создан: {dst}')
    return dst


def migrate_sqlite(db_path: str) -> None:
    import sqlite3

    if not os.path.exists(db_path):
        print(f'❌ БД не найдена: {db_path}', file=sys.stderr)
        sys.exit(1)

    print('=' * 60)
    print('🔄 Migration: add_vsosh9_method_fields (SQLite)')
    print(f'   БД: {db_path}')
    print('=' * 60)

    _sqlite_backup(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')

    try:
        for table, column, sqlite_sql, _pg_sql in ADDITIONS:
            if not _sqlite_table_exists(conn, table):
                print(f'⚠️  Таблица {table!r} ещё не создана — пропускаем колонку {column!r}.')
                continue
            if _sqlite_column_exists(conn, table, column):
                print(f'✅ {table}.{column} уже существует — пропускаем.')
                continue
            print(f'🔧 ALTER TABLE {table} ADD COLUMN {column}')
            conn.execute(sqlite_sql)
        conn.commit()
        print('✅ Миграция SQLite применена.')
    except Exception as e:
        conn.rollback()
        print(f'❌ Миграция SQLite упала: {e}', file=sys.stderr)
        sys.exit(2)
    finally:
        conn.close()


# ── PostgreSQL path ──────────────────────────────────────────────────────────

def migrate_postgres(dsn: str) -> None:
    try:
        import psycopg  # psycopg 3.x уже в requirements
    except ImportError:
        print('❌ psycopg не установлен. pip install "psycopg[binary]"', file=sys.stderr)
        sys.exit(3)

    print('=' * 60)
    print('🔄 Migration: add_vsosh9_method_fields (PostgreSQL)')
    print(f'   DSN: {dsn[:32]}…')
    print('=' * 60)

    with psycopg.connect(dsn, autocommit=False) as conn:
        try:
            with conn.cursor() as cur:
                for table, column, _sqlite_sql, pg_sql in ADDITIONS:
                    print(f'🔧 {pg_sql}')
                    cur.execute(pg_sql)
            conn.commit()
            print('✅ Миграция PostgreSQL применена.')
        except Exception as e:
            conn.rollback()
            print(f'❌ Миграция PostgreSQL упала: {e}', file=sys.stderr)
            sys.exit(4)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        '--db', default=None,
        help='Путь к sqlite-БД (по умолчанию formyla.db в корне репозитория).',
    )
    parser.add_argument(
        '--pg', nargs='?', const='', default=None,
        help='Использовать PostgreSQL. Без значения — берётся env DATABASE_URL.',
    )
    args = parser.parse_args()

    if args.pg is not None:
        dsn = args.pg or os.environ.get('DATABASE_URL', '')
        if not dsn:
            print('❌ Нужен DSN: --pg postgres://... или env DATABASE_URL.',
                  file=sys.stderr)
            sys.exit(1)
        migrate_postgres(dsn)
        return

    if args.db:
        db_path = args.db
    else:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # Flask кладёт SQLite в instance/ по умолчанию; берём её приоритетом.
        instance_db = os.path.join(project_root, 'instance', 'formyla.db')
        root_db = os.path.join(project_root, 'formyla.db')
        db_path = instance_db if os.path.exists(instance_db) else root_db
    migrate_sqlite(db_path)


if __name__ == '__main__':
    main()
