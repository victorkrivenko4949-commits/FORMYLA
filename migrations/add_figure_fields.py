#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: добавление полей figure_json и figure_status в таблицу adaptive_tasks.

Запуск:
    python migrations/add_figure_fields.py

Также экспортирует _ensure_table(), которая вызывается из app.py
при старте (auto-migration).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_sql_statements(dialect_name):
    """Сгенерировать DDL под конкретный SQL-диалект."""
    is_pg = dialect_name == "postgresql"
    bool_default = "DEFAULT 'no_description'" if is_pg else "DEFAULT 'no_description'"

    statements = [
        # figure_json — TEXT nullable, описание построений в JSON-формате geometric_engine
        "ALTER TABLE adaptive_tasks ADD COLUMN figure_json TEXT",
        # figure_status — VARCHAR(32) NOT NULL DEFAULT 'no_description'
        # Значения: no_description, has_description, figure_built,
        #           engine_rejected, human_verified, human_rejected
        f"ALTER TABLE adaptive_tasks ADD COLUMN figure_status VARCHAR(32) NOT NULL {bool_default}",
    ]

    if not is_pg:
        statements.append(
            "CREATE INDEX IF NOT EXISTS ix_adaptive_tasks_figure_status "
            "ON adaptive_tasks(figure_status)"
        )
    else:
        statements.append(
            "CREATE INDEX IF NOT EXISTS ix_adaptive_tasks_figure_status "
            "ON adaptive_tasks(figure_status)"
        )

    return statements


def _ensure_table() -> bool:
    """Добавляет колонки figure_json и figure_status, если их нет. Идемпотентно.

    Вызывается из app.py при старте (auto-migration).
    """
    from app import app
    from models import db
    from sqlalchemy import text, inspect

    with app.app_context():
        dialect = db.engine.dialect.name
        print(f"  [figure_fields migration] dialect = {dialect}")

        inspector = inspect(db.engine)
        if 'adaptive_tasks' not in inspector.get_table_names():
            print("  [figure_fields migration] adaptive_tasks table not found — skip")
            return True

        columns = [col['name'] for col in inspector.get_columns('adaptive_tasks')]

        new_cols = {
            'figure_json': 'TEXT',
            'figure_status': "VARCHAR(32) NOT NULL DEFAULT 'no_description'",
        }

        for col_name, col_type in new_cols.items():
            if col_name not in columns:
                try:
                    db.session.execute(
                        text(f"ALTER TABLE adaptive_tasks ADD COLUMN {col_name} {col_type}")
                    )
                    db.session.commit()
                    print(f"  ✅ [figure_fields] Column '{col_name}' added")
                except Exception as e:
                    db.session.rollback()
                    print(f"  ❌ [figure_fields] Column '{col_name}' failed: {e}")
                    return False
            else:
                print(f"  ✅ [figure_fields] Column '{col_name}' already exists")

        # Ensure index
        if dialect == "sqlite":
            try:
                db.session.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_adaptive_tasks_figure_status "
                    "ON adaptive_tasks(figure_status)"
                ))
                db.session.commit()
            except Exception:
                db.session.rollback()

        return True


def run_migration() -> bool:
    """Запуск миграции с подробным выводом."""
    print("=" * 70)
    print("МИГРАЦИЯ: figure_json + figure_status для adaptive_tasks")
    print("=" * 70)
    success = _ensure_table()
    if success:
        print("\n🎉 Миграция figure_fields завершена успешно!")
    else:
        print("\n❌ Миграция figure_fields завершилась с ошибками")
    return success


if __name__ == "__main__":
    sys.exit(0 if run_migration() else 1)
