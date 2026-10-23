# -*- coding: utf-8 -*-
"""
Idempotent migration: добавить telegram_id + telegram_username в таблицу users.

Запуск:
    # SQLite (по умолчанию использует instance/formyla.db)
    python migrations/add_telegram_id_to_user.py

    # PostgreSQL — через переменную окружения DATABASE_URL
    python migrations/add_telegram_id_to_user.py --pg

Скрипт безопасно проходит повторный запуск: если колонка уже есть, он её
пропустит. Не удаляет данные.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _resolve_sqlite_path() -> str:
    """Приоритет — instance/formyla.db (реальная БД), затем корневой formyla.db."""
    instance_db = ROOT / "instance" / "formyla.db"
    if instance_db.exists():
        return str(instance_db)
    root_db = ROOT / "formyla.db"
    return str(root_db)


def _sqlite_has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in cur.fetchall())


def migrate_sqlite(db_path: str) -> None:
    print(f"[sqlite] DB: {db_path}")
    if not Path(db_path).exists():
        print(f"[sqlite] WARN: file does not exist — будет создан Flask при первом запуске")
        return

    conn = sqlite3.connect(db_path)
    try:
        added = []
        if not _sqlite_has_column(conn, "users", "telegram_id"):
            conn.execute("ALTER TABLE users ADD COLUMN telegram_id VARCHAR(64)")
            added.append("telegram_id")
        if not _sqlite_has_column(conn, "users", "telegram_username"):
            conn.execute("ALTER TABLE users ADD COLUMN telegram_username VARCHAR(64)")
            added.append("telegram_username")
        # Уникальный индекс по telegram_id (через WHERE для совместимости с NULL).
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_id "
            "ON users (telegram_id) WHERE telegram_id IS NOT NULL"
        )
        conn.commit()
        if added:
            print(f"[sqlite] OK: добавлены колонки: {', '.join(added)}")
        else:
            print("[sqlite] OK: колонки уже существуют (no-op)")
    finally:
        conn.close()


def migrate_postgres(dsn: str) -> None:
    try:
        import psycopg
    except ImportError:
        print("[pg] FAIL: psycopg не установлен. pip install 'psycopg[binary]'")
        sys.exit(1)

    print("[pg] DSN: ***")
    with psycopg.connect(dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS telegram_id VARCHAR(64),
                    ADD COLUMN IF NOT EXISTS telegram_username VARCHAR(64)
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_id
                    ON users (telegram_id)
                    WHERE telegram_id IS NOT NULL
            """)
        conn.commit()
        print("[pg] OK: telegram_id, telegram_username + unique index готовы")


def main() -> None:
    parser = argparse.ArgumentParser(description="Add telegram_id / telegram_username to users")
    parser.add_argument("--pg", action="store_true", help="Apply to PostgreSQL via DATABASE_URL")
    parser.add_argument("--db", help="Override SQLite path")
    args = parser.parse_args()

    if args.pg:
        dsn = os.environ.get("DATABASE_URL", "").strip()
        if not dsn:
            print("[pg] FAIL: DATABASE_URL is not set")
            sys.exit(1)
        if dsn.startswith("postgres://"):
            dsn = dsn.replace("postgres://", "postgresql://", 1)
        migrate_postgres(dsn)
    else:
        path = args.db or _resolve_sqlite_path()
        migrate_sqlite(path)


if __name__ == "__main__":
    main()