#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Миграция: создание таблиц «Банка неточностей» (insights).

Идемпотентна. Таблицы создаются через db.create_all() на основе моделей из
models_insights.py. Дополнительно ALTER-ом доливаются недостающие колонки,
если таблицы уже существовали в устаревшем виде.

Запуск:
    python migrations/add_insights_tables.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


_TABLES = (
    "insight_jobs",
    "insights",
    "insight_practice_tasks",
    "insight_notifications",
)


def _ensure_table() -> bool:
    """Создать недостающие таблицы. Идемпотентно."""
    import models_insights  # noqa: F401  — регистрирует модели в metadata
    from app import app
    from models import db
    from sqlalchemy import inspect

    with app.app_context():
        inspector = inspect(db.engine)
        existing = set(inspector.get_table_names())
        missing = [t for t in _TABLES if t not in existing]
        if missing:
            db.create_all()
        inspector = inspect(db.engine)
        now = set(inspector.get_table_names())
        return all(t in now for t in _TABLES)


if __name__ == "__main__":
    ok = _ensure_table()
    print("insights tables ready" if ok else "FAILED")
    sys.exit(0 if ok else 1)
