#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: создание таблиц для пайплайна регенерации Адаптивного теста.

Таблицы:
  - task_generation_log     — все попытки генерации (успехи и неудачи)
  - manual_review_queue     — задачи, не прошедшие 4 итерации (требуют ручной проверки)
  - cost_log                — токены × цена для каждого вызова модели

Запуск:
    python migrations/add_adaptive_pipeline_tables.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


SQL_STATEMENTS = [
    # ─── task_generation_log ───────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS task_generation_log (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id                VARCHAR(36)  NOT NULL,
        subject               VARCHAR(50)  NOT NULL,
        grade                 INTEGER      NOT NULL,
        level                 INTEGER      NOT NULL,
        success               INTEGER      NOT NULL DEFAULT 0,
        iterations_used       INTEGER      NOT NULL DEFAULT 0,
        total_input_tokens    INTEGER      NOT NULL DEFAULT 0,
        total_output_tokens   INTEGER      NOT NULL DEFAULT 0,
        total_cost_usd        REAL         NOT NULL DEFAULT 0.0,
        saved_task_id         INTEGER,
        sent_to_review        INTEGER      NOT NULL DEFAULT 0,
        iterations_detail_json TEXT,
        error                 TEXT,
        created_at            DATETIME     DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_tgl_run_id  ON task_generation_log(run_id)",
    "CREATE INDEX IF NOT EXISTS ix_tgl_subject ON task_generation_log(subject)",
    "CREATE INDEX IF NOT EXISTS ix_tgl_success ON task_generation_log(success)",
    "CREATE INDEX IF NOT EXISTS ix_tgl_grade_level ON task_generation_log(grade, level)",

    # ─── manual_review_queue ────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS manual_review_queue (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id          VARCHAR(36)  NOT NULL,
        subject         VARCHAR(50)  NOT NULL,
        grade           INTEGER      NOT NULL,
        level           INTEGER      NOT NULL,
        task_json       TEXT         NOT NULL,
        validator_json  TEXT,
        calibrator_json TEXT,
        reason          VARCHAR(200),
        status          VARCHAR(20)  NOT NULL DEFAULT 'pending',
        reviewer_notes  TEXT,
        reviewed_at     DATETIME,
        created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_mrq_status      ON manual_review_queue(status)",
    "CREATE INDEX IF NOT EXISTS ix_mrq_subject     ON manual_review_queue(subject)",
    "CREATE INDEX IF NOT EXISTS ix_mrq_run_id      ON manual_review_queue(run_id)",

    # ─── cost_log ──────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS cost_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id          VARCHAR(36)  NOT NULL,
        stage           VARCHAR(20)  NOT NULL,
        model           VARCHAR(100) NOT NULL,
        input_tokens    INTEGER      NOT NULL DEFAULT 0,
        output_tokens   INTEGER      NOT NULL DEFAULT 0,
        cost_usd        REAL         NOT NULL DEFAULT 0.0,
        latency_s       REAL         NOT NULL DEFAULT 0.0,
        created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_cost_run_id ON cost_log(run_id)",
    "CREATE INDEX IF NOT EXISTS ix_cost_model  ON cost_log(model)",
    "CREATE INDEX IF NOT EXISTS ix_cost_stage  ON cost_log(stage)",
]


def run_migration() -> bool:
    """Создаёт таблицы пайплайна, если их нет."""
    from app import app
    from models import db
    from sqlalchemy import text, inspect

    with app.app_context():
        for stmt in SQL_STATEMENTS:
            db.session.execute(text(stmt))
        db.session.commit()

        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        ok = True
        for expected in ("task_generation_log", "manual_review_queue", "cost_log"):
            if expected in tables:
                cols = [c["name"] for c in inspector.get_columns(expected)]
                print(f"[OK] {expected}: {len(cols)} колонок")
            else:
                print(f"[ERROR] {expected} НЕ создана!")
                ok = False

        return ok


if __name__ == "__main__":
    print("=" * 70)
    print("МИГРАЦИЯ: Adaptive Pipeline Tables")
    print("=" * 70)
    success = run_migration()
    if success:
        print("\n Миграция завершена успешно!")
        sys.exit(0)
    else:
        print("\n[ERROR] Миграция завершилась с ошибками")
        sys.exit(1)
