#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: создание таблиц для раздела «Задачи дня» (Daily Tasks).

Таблицы (3 шт., см. daily_tasks/models.py):
  - daily_task_sets          — один сет на пользователя на день
  - daily_task_items         — 10 задач внутри сета
  - daily_generation_jobs    — фоновый джоб генерации

Запуск:
    python migrations/add_daily_tasks_tables.py

Также экспортирует _ensure_table(), которая вызывается из app.py
при регистрации bluepint (auto-migration на старте).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ──────────────────────────────────────────────────────────────────────────
# 2026-05-29: миграция приведена к совместимости с SQLite и PostgreSQL.
#
# Старый вариант использовал SQLite-специфичный синтаксис
#   INTEGER PRIMARY KEY AUTOINCREMENT
# который PostgreSQL не понимает. На Render это приводило к падению
# _ensure_table() при первом запросе, и весь try-блок регистрации
# daily_tasks_bp в app.py молча проглатывал ошибку. Итог: /daily_tasks
# отдавал 404, а url_for('daily_tasks.get_daily_tasks') в шапке
# рушил рендеринг — пользователя кидало в случайный раздел.
#
# Теперь SQL генерируется отдельно для каждого диалекта.
# ──────────────────────────────────────────────────────────────────────────


def _build_sql_statements(dialect_name):
    """Сгенерировать DDL под конкретный SQL-диалект.

    dialect_name — SQLAlchemy engine.dialect.name (например 'sqlite', 'postgresql').
    """
    is_pg = dialect_name == "postgresql"

    # тип PRIMARY KEY автоинкремент — у каждого диалекта свой
    pk = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    # PostgreSQL: TIMESTAMP; SQLite: DATETIME (оба алиасы)
    dt = "TIMESTAMP" if is_pg else "DATETIME"
    # PostgreSQL: BOOLEAN с DEFAULT FALSE; SQLite: BOOLEAN с DEFAULT 0
    bool_false = "FALSE" if is_pg else "0"

    statements = [
        # ─── daily_task_sets ───────────────────────────────────────────────
        f"""
        CREATE TABLE IF NOT EXISTS daily_task_sets (
            id              {pk},
            user_id         INTEGER  NOT NULL,
            target_date     DATE     NOT NULL,
            class_level     INTEGER,
            status          VARCHAR(32) NOT NULL DEFAULT 'pending',
            generated_at    {dt},
            triggered_by    VARCHAR(64),
            reason_summary  TEXT,
            pipeline_log    TEXT,
            total_cost_usd  FLOAT    NOT NULL DEFAULT 0.0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_dts_user_id      ON daily_task_sets(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_dts_target_date   ON daily_task_sets(target_date)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_dts_user_date ON daily_task_sets(user_id, target_date)",

        # ─── daily_task_items ──────────────────────────────────────────────
        f"""
        CREATE TABLE IF NOT EXISTS daily_task_items (
            id                {pk},
            daily_set_id      INTEGER  NOT NULL,
            position          INTEGER  NOT NULL,
            slot_kind         VARCHAR(32),
            subject           VARCHAR(100),
            topic             VARCHAR(200),
            subtopic          VARCHAR(100),
            difficulty_level  INTEGER,
            weakness_score    FLOAT,
            reason            TEXT,
            task_text         TEXT     NOT NULL,
            correct_answer    TEXT,
            solution          TEXT,
            hints             TEXT,
            gemini_spec_json  TEXT,
            opus_iterations   INTEGER  NOT NULL DEFAULT 0,
            gpt_audit_json    TEXT,
            is_flagged        BOOLEAN  NOT NULL DEFAULT {bool_false},
            flag_reason       TEXT,
            status            VARCHAR(32) NOT NULL DEFAULT 'pending',
            user_answer       TEXT,
            is_correct        BOOLEAN,
            answered_at       {dt},
            time_spent_seconds INTEGER,
            FOREIGN KEY (daily_set_id) REFERENCES daily_task_sets(id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_dti_daily_set_id ON daily_task_items(daily_set_id)",
        "CREATE INDEX IF NOT EXISTS ix_dti_status       ON daily_task_items(status)",

        # ─── daily_generation_jobs ─────────────────────────────────────────
        f"""
        CREATE TABLE IF NOT EXISTS daily_generation_jobs (
            id              {pk},
            user_id         INTEGER  NOT NULL,
            target_date     DATE     NOT NULL,
            daily_set_id    INTEGER,
            state           VARCHAR(32) NOT NULL DEFAULT 'queued',
            current_step    VARCHAR(64),
            progress_pct    INTEGER  NOT NULL DEFAULT 0,
            error_message   TEXT,
            started_at      {dt},
            finished_at     {dt},
            created_at      {dt} NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)      REFERENCES users(id),
            FOREIGN KEY (daily_set_id) REFERENCES daily_task_sets(id) ON DELETE SET NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_dgj_user_id      ON daily_generation_jobs(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_dgj_target_date   ON daily_generation_jobs(target_date)",
        "CREATE INDEX IF NOT EXISTS ix_dgj_state         ON daily_generation_jobs(state)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_dgj_user_date ON daily_generation_jobs(user_id, target_date)",
    ]
    return statements


# Старая константа SQL_STATEMENTS оставлена для обратной совместимости
# с теми скриптами, что её импортировали напрямую (SQLite-вариант).
SQL_STATEMENTS = _build_sql_statements("sqlite")


def _ensure_table() -> bool:
    """Создаёт таблицы Daily Tasks, если их нет. Идемпотентно.

    Вызывается из app.py при регистрации blueprint (auto-migration).
    Поддерживает SQLite (локально) и PostgreSQL (Render).
    """
    from app import app
    from models import db
    from sqlalchemy import text, inspect

    with app.app_context():
        dialect = db.engine.dialect.name
        print(f"  [daily_tasks migration] dialect = {dialect}")
        statements = _build_sql_statements(dialect)

        for stmt in statements:
            try:
                db.session.execute(text(stmt))
            except Exception as e:
                # Если конкретный statement упал — НЕ глотаем тихо,
                # делаем rollback и пробрасываем дальше, чтобы наружу
                # ушла понятная ошибка вместо бесшумно пропавшего blueprint.
                db.session.rollback()
                print(f"  [ERROR] daily_tasks migration: failed on stmt: {e}")
                raise
        db.session.commit()

        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        ok = True
        for expected in ("daily_task_sets", "daily_task_items", "daily_generation_jobs"):
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
    print("МИГРАЦИЯ: Daily Tasks Tables")
    print("=" * 70)
    success = _ensure_table()
    if success:
        print("\n Миграция завершена успешно!")
    else:
        print("\n[ERROR] Миграция завершилась с ошибками")
    return success


if __name__ == "__main__":
    sys.exit(0 if run_migration() else 1)
