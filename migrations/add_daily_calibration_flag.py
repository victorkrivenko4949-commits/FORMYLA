#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: добавить поле ``is_calibration`` в таблицу ``daily_task_items``.

Связана с PR "percent_to_level + calibration" (ТЗ от 2026-06-08).
Поле помечает задачи дня, которые сгенерированы по темам БЕЗ пройденного
диагностического теста (т.е. для постепенной достройки профиля).

Совместима с SQLite и PostgreSQL.

Запуск вручную:
    python migrations/add_daily_calibration_flag.py

Автоматический запуск: импортируем _ensure_calibration_column() из app.py
при регистрации daily_tasks blueprint (как и другие auto-migrations).
"""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


def _column_exists(conn, table: str, column: str, dialect: str) -> bool:
    """Проверить, есть ли колонка в таблице."""
    if dialect == "postgresql":
        sql = (
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        )
        from sqlalchemy import text
        res = conn.execute(text(sql), {"t": table, "c": column}).first()
        return res is not None
    # sqlite
    from sqlalchemy import text
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def _ensure_calibration_column(db) -> None:
    """Идемпотентная auto-migration: добавляет колонку ``is_calibration``.

    Вызывается из ``app.py`` при регистрации daily_tasks_bp.
    """
    from sqlalchemy import text
    dialect = db.engine.dialect.name
    with db.engine.begin() as conn:
        if _column_exists(conn, "daily_task_items", "is_calibration", dialect):
            logger.info(
                "daily_task_items.is_calibration already exists — skip"
            )
            return

        if dialect == "postgresql":
            sql = (
                "ALTER TABLE daily_task_items "
                "ADD COLUMN is_calibration BOOLEAN NOT NULL DEFAULT FALSE"
            )
        else:
            # SQLite: ALTER TABLE … ADD COLUMN — поддерживается.
            sql = (
                "ALTER TABLE daily_task_items "
                "ADD COLUMN is_calibration BOOLEAN NOT NULL DEFAULT 0"
            )
        logger.info("Adding column daily_task_items.is_calibration (%s)", dialect)
        conn.execute(text(sql))


def run() -> None:
    """CLI-entry: открываем Flask-app context и запускаем _ensure_*."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # импорт app тут, чтобы при импорте модуля как auto-migration
    # не падать на отсутствии Flask-окружения
    from app import app  # type: ignore
    from models import db  # type: ignore
    with app.app_context():
        _ensure_calibration_column(db)
        print("[OK] Migration done: daily_task_items.is_calibration ensured")


if __name__ == "__main__":
    run()
