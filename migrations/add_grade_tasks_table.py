# -*- coding: utf-8 -*-
"""Миграция: создание таблицы grade_tasks для разделов /grade-5, /grade-6.

Создаёт одну таблицу `grade_tasks` под 1600 задач 5–6 классов.

Запуск:
    python migrations/add_grade_tasks_table.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import db  # noqa: E402
from models_grade import GradeTask  # noqa: E402,F401  (register model)
from app import app  # noqa: E402

EXPECTED = [GradeTask.__tablename__]


def migrate() -> int:
    with app.app_context():
        print('Migration: create grade_tasks…')
        try:
            db.create_all()
        except Exception as exc:
            print(f'ERROR create_all(): {exc!r}')
            db.session.rollback()
            return 1
        insp = db.inspect(db.engine)
        names = set(insp.get_table_names())
        missing = [t for t in EXPECTED if t not in names]
        if missing:
            print('ERROR: tables not created:', missing)
            return 1
        print('OK. tables:', EXPECTED)
        return 0


if __name__ == '__main__':
    sys.exit(migrate())
