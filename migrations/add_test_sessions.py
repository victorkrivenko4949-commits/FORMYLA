#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: таблица test_sessions для восстановления незавершённых
адаптивных тестов.

Таблица (1 шт.):
  - test_sessions — сохраняет полное состояние сессии адаптивного теста

Запуск:
    python migrations/add_test_sessions.py

Также экспортирует _ensure_test_sessions_table(), которая вызывается из app.py
при старте (auto-migration).
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
    # JSONB vs TEXT (SQLite не имеет JSONB)
    json_type = "JSONB" if is_pg else "TEXT"

    statements = [
        f"""
        CREATE TABLE IF NOT EXISTS test_sessions (
            id                      {pk},
            user_id                 INTEGER,
            device_id               VARCHAR(64),

            -- Идентификация теста
            test_type               VARCHAR(32)  NOT NULL,
            topic                   VARCHAR(64),
            topic_name              VARCHAR(128),
            grade                   VARCHAR(8),

            -- Прогресс
            status                  VARCHAR(20)  NOT NULL DEFAULT 'in_progress',
            current_question_index  INTEGER      NOT NULL DEFAULT 0,
            total_questions         INTEGER      NOT NULL DEFAULT 25,

            -- Полное состояние (JSON)
            answers                 {json_type},
            adaptive_state          {json_type},

            -- Результат
            current_result          INTEGER      DEFAULT 0,

            -- Таймстемпы
            started_at              {dt} DEFAULT CURRENT_TIMESTAMP,
            last_activity_at        {dt} DEFAULT CURRENT_TIMESTAMP,
            completed_at            {dt},

            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """,
    ]

    if is_pg:
        # PostgreSQL: partial unique index — один in_progress на (user_id, test_type)
        statements.append(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_ts_one_in_progress "
            "ON test_sessions(user_id, test_type) WHERE status = 'in_progress'"
        )
        # Индекс для поиска по device_id (гости)
        statements.append(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_ts_one_in_progress_device "
            "ON test_sessions(device_id, test_type) "
            "WHERE device_id IS NOT NULL AND status = 'in_progress'"
        )
        # Общие индексы
        statements.append(
            "CREATE INDEX IF NOT EXISTS idx_ts_user_status ON test_sessions(user_id, status)"
        )
        statements.append(
            "CREATE INDEX IF NOT EXISTS idx_ts_device_status ON test_sessions(device_id, status)"
        )
    else:
        # SQLite: обычные индексы (partial unique не поддерживается)
        statements.append(
            "CREATE INDEX IF NOT EXISTS idx_ts_user_status ON test_sessions(user_id, status)"
        )
        statements.append(
            "CREATE INDEX IF NOT EXISTS idx_ts_device_status ON test_sessions(device_id, status)"
        )
        # Индекс для быстрого поиска: один in_progress на (user_id, test_type)
        # (уникальность гарантируется на уровне приложения)
        statements.append(
            "CREATE INDEX IF NOT EXISTS idx_ts_user_type_status "
            "ON test_sessions(user_id, test_type, status)"
        )

    return statements


def _ensure_test_sessions_table() -> bool:
    """Создаёт таблицу test_sessions, если её нет.

    Вызывается из app.py при старте (auto-migration).
    Поддерживает SQLite (локально) и PostgreSQL (Render).
    """
    from app import app
    from models import db
    from sqlalchemy import text, inspect

    with app.app_context():
        dialect = db.engine.dialect.name
        print(f"  [test_sessions migration] dialect = {dialect}")
        statements = _build_sql_statements(dialect)

        for stmt in statements:
            try:
                db.session.execute(text(stmt))
            except Exception as e:
                db.session.rollback()
                print(f"  [ERROR] test_sessions migration: failed on stmt: {e}")
                raise
        db.session.commit()

        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        ok = True
        for expected in ("test_sessions",):
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
    print("МИГРАЦИЯ: Test Sessions Table")
    print("=" * 70)
    success = _ensure_test_sessions_table()
    if success:
        print("\n Миграция test_sessions завершена успешно!")
    else:
        print("\n[ERROR] Миграция завершилась с ошибками")
    return success


if __name__ == "__main__":
    sys.exit(0 if run_migration() else 1)
