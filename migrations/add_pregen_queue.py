#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: создание таблицы pre_gen_queue для очереди предгенерации задач на завтра.

Таблица (см. daily_tasks/models.py PreGenQueue):
  - pre_gen_queue — очередь предгенерации задач на завтра

Запуск:
    python migrations/add_pregen_queue.py

Также экспортирует _ensure_table(), которая вызывается из app.py
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

    statements = [
        # ─── pre_gen_queue ──────────────────────────────────────────────────
        f"""
        CREATE TABLE IF NOT EXISTS pre_gen_queue (
            id              {pk},
            user_id         INTEGER  NOT NULL,
            target_date     DATE     NOT NULL,
            cache_key       VARCHAR(64) NOT NULL,
            pool_id         INTEGER,
            status          VARCHAR(16) NOT NULL DEFAULT 'queued',
            profile_json    TEXT,
            release_at      {dt},
            expires_at      {dt},
            created_at      {dt} NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      {dt},
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (pool_id) REFERENCES task_pool(id) ON DELETE SET NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_pgq_user_id      ON pre_gen_queue(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_pgq_target_date  ON pre_gen_queue(target_date)",
        "CREATE INDEX IF NOT EXISTS ix_pgq_cache_key    ON pre_gen_queue(cache_key)",
        "CREATE INDEX IF NOT EXISTS ix_pgq_pool_id      ON pre_gen_queue(pool_id)",
        "CREATE INDEX IF NOT EXISTS ix_pgq_status       ON pre_gen_queue(status)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_pgq_user_date ON pre_gen_queue(user_id, target_date)",
    ]
    return statements


def _ensure_table() -> bool:
    """Создаёт таблицу pre_gen_queue, если её нет. Идемпотентно.

    Вызывается из app.py при старте (auto-migration).
    Поддерживает SQLite (локально) и PostgreSQL (Render).
    """
    from app import app
    from models import db
    from sqlalchemy import text, inspect

    with app.app_context():
        dialect = db.engine.dialect.name
        print(f"  [pregen_queue migration] dialect = {dialect}")
        statements = _build_sql_statements(dialect)

        for stmt in statements:
            try:
                db.session.execute(text(stmt))
            except Exception as e:
                db.session.rollback()
                print(f"  ❌ pregen_queue migration: failed on stmt: {e}")
                raise
        db.session.commit()

        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        ok = True
        if "pre_gen_queue" in tables:
            cols = [c["name"] for c in inspector.get_columns("pre_gen_queue")]
            print(f"  ✅ pre_gen_queue: {len(cols)} колонок")
        else:
            print("  ❌ pre_gen_queue НЕ создана!")
            ok = False

        return ok


def run_migration() -> bool:
    """Запуск миграции с подробным выводом."""
    print("=" * 70)
    print("МИГРАЦИЯ: PreGenQueue Table")
    print("=" * 70)
    success = _ensure_table()
    if success:
        print("\n🎉 Миграция завершена успешно!")
    else:
        print("\n❌ Миграция завершилась с ошибками")
    return success


if __name__ == "__main__":
    sys.exit(0 if run_migration() else 1)
