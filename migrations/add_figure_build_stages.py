#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: создание таблицы figure_build_stages (телеметрия стадий генерации
чертежа, CH22) + колонки visual_check.  Идемпотентна.

Запуск:
    python migrations/add_figure_build_stages.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Колонки visual_check, добавляемые ALTER TABLE (для уже существующей таблицы).
_VISUAL_COLUMNS = [
    ("visual_score", "FLOAT"),
    ("label_collisions", "INTEGER DEFAULT 0"),
    ("autofix_applied", "BOOLEAN DEFAULT 0"),
    ("reseed_count", "INTEGER DEFAULT 0"),
    # REC-7: reasoning-токены и флаги fallback/timeout.
    ("reasoning_tokens", "INTEGER"),
    ("fallback_used", "BOOLEAN DEFAULT 0"),
    ("timeout_hit", "BOOLEAN DEFAULT 0"),
]

# CH-aux: колонки solver-driven aux в figure_build_jobs.
_JOB_COLUMNS = [
    ("solution_json", "TEXT"),
    ("solver_answer", "VARCHAR(64)"),
    ("measured_answer", "VARCHAR(64)"),
    ("answer_verdict", "VARCHAR(16)"),
    ("trust_level", "VARCHAR(16)"),
    ("aux_source", "VARCHAR(16)"),
    ("aux_usefulness", "FLOAT"),
    ("aux_dropped_reason", "VARCHAR(64)"),
    # completeness_check (Gemini vision).
    ("aux_completeness", "INTEGER"),
]


def _ensure_table() -> bool:
    """Создать таблицу + добавить недостающие колонки. Идемпотентно."""
    from app import app
    from models import db
    from sqlalchemy import text, inspect

    with app.app_context():
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        # 1. Таблица.
        if "figure_build_stages" not in tables:
            db.create_all()

        inspector = inspect(db.engine)
        cols = {c["name"] for c in inspector.get_columns("figure_build_stages")}

        # 2. Колонки визуального аудита.
        for name, ctype in _VISUAL_COLUMNS:
            if name not in cols:
                db.session.execute(text(
                    f"ALTER TABLE figure_build_stages ADD COLUMN {name} {ctype}"
                ))

        # 3. Колонки solver-aux в figure_build_jobs.
        if "figure_build_jobs" in inspector.get_table_names():
            job_cols = {c["name"] for c in inspector.get_columns("figure_build_jobs")}
            for name, ctype in _JOB_COLUMNS:
                if name not in job_cols:
                    db.session.execute(text(
                        f"ALTER TABLE figure_build_jobs ADD COLUMN {name} {ctype}"
                    ))
        db.session.commit()

        inspector = inspect(db.engine)
        return "figure_build_stages" in inspector.get_table_names()


if __name__ == "__main__":
    ok = _ensure_table()
    print("figure_build_stages table ready" if ok else "FAILED")
    sys.exit(0 if ok else 1)
