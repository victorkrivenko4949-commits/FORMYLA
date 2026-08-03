#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: таблицы кэширования пула задач «Задачи дня».

Таблицы (2 шт.):
  - task_pool                — общий пул сгенерированных наборов (10 задач)
  - user_task_assignments    — привязка пользователя к пулу (какие 10 из 10 взял)

Запуск:
    python migrations/add_task_pool_cache.py

Также экспортирует _ensure_task_pool_tables(), которая вызывается из app.py
при регистрации blueprint (auto-migration на старте).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_sql_statements(dialect_name):
    """Сгенерировать DDL под конкретный SQL-диалект.

    dialect_name — SQLAlchemy engine.dialect.name (например 'sqlite', 'postgresql').
    """
    is_pg = dialect_name == "postgresql"

    # тип PRIMARY KEY автоинкремент — у каждого диалекта свой
    pk = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    # PostgreSQL: TIMESTAMP; SQLite: DATETIME (оба алиасы)
    dt = "TIMESTAMP" if is_pg else "DATETIME"

    statements = [
        # ─── task_pool ──────────────────────────────────────────────────────
        f"""
        CREATE TABLE IF NOT EXISTS task_pool (
            id              {pk},
            cache_key       VARCHAR(64)  NOT NULL,
            subject         VARCHAR(32)  NOT NULL,
            grade           SMALLINT     NOT NULL,
            profile_snapshot TEXT         NOT NULL,
            tasks           TEXT         NOT NULL,
            specs           TEXT         NOT NULL,
            status          VARCHAR(16)  NOT NULL,
            valid_count     SMALLINT     NOT NULL,
            created_at      {dt} DEFAULT CURRENT_TIMESTAMP,
            used_count      INTEGER      DEFAULT 0,
            expires_at      {dt}
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_task_pool_cache_key ON task_pool(cache_key)",
        "CREATE INDEX IF NOT EXISTS idx_task_pool_expires   ON task_pool(expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_task_pool_lookup    ON task_pool(cache_key, status, expires_at)",

        # ─── user_task_assignments ──────────────────────────────────────────
        f"""
        CREATE TABLE IF NOT EXISTS user_task_assignments (
            id              {pk},
            user_id         INTEGER  NOT NULL,
            pool_id         INTEGER  NOT NULL,
            task_positions  TEXT     NOT NULL,
            assigned_at     {dt} DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (pool_id) REFERENCES task_pool(id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_uta_user  ON user_task_assignments(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_uta_pool  ON user_task_assignments(pool_id)",
    ]
    return statements


def _ensure_task_pool_tables() -> bool:
    """Создаёт таблицы task_pool и user_task_assignments, если их нет.

    Вызывается из app.py при регистрации blueprint (auto-migration).
    Поддерживает SQLite (локально) и PostgreSQL (Render).
    """
    from app import app
    from models import db
    from sqlalchemy import text, inspect

    with app.app_context():
        dialect = db.engine.dialect.name
        print(f"  [task_pool migration] dialect = {dialect}")
        statements = _build_sql_statements(dialect)

        for stmt in statements:
            try:
                db.session.execute(text(stmt))
            except Exception as e:
                db.session.rollback()
                print(f"  [ERROR] task_pool migration: failed on stmt: {e}")
                raise
        db.session.commit()

        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        ok = True
        for expected in ("task_pool", "user_task_assignments"):
            if expected in tables:
                cols = [c["name"] for c in inspector.get_columns(expected)]
                print(f"  [OK] {expected}: {len(cols)} колонок")
            else:
                print(f"  [ERROR] {expected} НЕ создана!")
                ok = False

        return ok


def run_migration() -> bool:
    """Запуск миграции с подробным выводом."""
    print("=" * 70)
    print("МИГРАЦИЯ: Task Pool Cache Tables")
    print("=" * 70)
    success = _ensure_task_pool_tables()
    if success:
        print("\n Миграция кэша пула задач завершена успешно!")
    else:
        print("\n[ERROR] Миграция завершилась с ошибками")
    return success


if __name__ == "__main__":
    sys.exit(0 if run_migration() else 1)
