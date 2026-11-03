#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: добавить поле ``parent_invite_code`` в таблицу ``users``.

JOIN_CODE_V1 — код, по которому ученик привязывается к родителю со страницы
/join (в разделе «Прочее»). Поле nullable: код генерируется лениво при
первом заходе родителя на /parent, поэтому существующим строкам бэкфилл
не нужен.

Совместима с SQLite и PostgreSQL.

Запуск вручную:
    python migrations/add_parent_invite_code.py

Автоматический запуск: _ensure_parent_invite_code_column() вызывается из
app.py при регистрации parent_teacher_bp (как и другие auto-migrations).
"""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


def _column_exists(conn, table: str, column: str, dialect: str) -> bool:
    """Проверить, есть ли колонка в таблице."""
    from sqlalchemy import text

    if dialect == "postgresql":
        sql = (
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        )
        res = conn.execute(text(sql), {"t": table, "c": column}).first()
        return res is not None
    # sqlite
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def _ensure_parent_invite_code_column(db) -> None:
    """Идемпотентная auto-migration: добавляет колонку ``parent_invite_code``.

    Вызывается из ``app.py`` при регистрации parent_teacher_bp.
    """
    with db.engine.begin() as conn:
        dialect = conn.dialect.name
        if _column_exists(conn, "users", "parent_invite_code", dialect):
            return
        from sqlalchemy import text

        if dialect == "postgresql":
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN parent_invite_code VARCHAR(6)"
            ))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_parent_invite_code "
                "ON users (parent_invite_code)"
            ))
        else:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN parent_invite_code VARCHAR(6)"
            ))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_parent_invite_code "
                "ON users (parent_invite_code)"
            ))
        logger.info("[MIG] users.parent_invite_code added")


if __name__ == "__main__":
    from app import app, db  # noqa: F811
    with app.app_context():
        _ensure_parent_invite_code_column(db)
        print("[OK] users.parent_invite_code ensured")
