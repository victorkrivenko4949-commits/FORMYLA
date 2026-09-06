# -*- coding: utf-8 -*-
"""Миграция: добавить поля каталога методов в olympiad_theory.

Добавляет 4 колонки в таблицу `olympiad_theory`:
    - grades                    JSON  (массив классов 5..11)
    - recommended_competitions  JSON  (список названий олимпиад)
    - difficulty_level          INT   (1..4)
    - frequency_vsosh_9         INT   (0..10, частота на ВсОШ-9)
    - sort_order                INT   (порядок отображения в каталоге)

И два индекса для фильтров/сортировки:
    - ix_olympiad_theory_difficulty_level
    - ix_olympiad_theory_frequency_vsosh_9

Идемпотентна: проверяет наличие колонок/индексов и пропускает существующие.

Запуск:
    python migrations/add_methods_catalog_fields.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text  # noqa: E402

from models import db  # noqa: E402
import models_olympiad  # noqa: E402,F401  (register TheoryBlock)
from app import app  # noqa: E402


TABLE = 'olympiad_theory'

NEW_COLUMNS = [
    ('grades',                   'JSON'),
    ('recommended_competitions', 'JSON'),
    ('difficulty_level',         'INTEGER'),
    ('frequency_vsosh_9',        'INTEGER'),
    ('sort_order',               'INTEGER DEFAULT 0'),
]

NEW_INDEXES = [
    ('ix_olympiad_theory_difficulty_level',   ['difficulty_level']),
    ('ix_olympiad_theory_frequency_vsosh_9',  ['frequency_vsosh_9']),
    ('ix_olympiad_theory_sort_order',         ['sort_order']),
]


def migrate() -> int:
    with app.app_context():
        insp = inspect(db.engine)
        if TABLE not in insp.get_table_names():
            print('ERROR: table {0} does not exist. '
                  'Run migrations/add_olympiad_section.py first.'.format(TABLE))
            return 1

        existing_cols = {c['name'] for c in insp.get_columns(TABLE)}
        existing_idx = {i['name'] for i in insp.get_indexes(TABLE)}

        added_cols = []
        for name, sql_type in NEW_COLUMNS:
            if name in existing_cols:
                print('  - column {0} already exists, skip'.format(name))
                continue
            stmt = 'ALTER TABLE {0} ADD COLUMN {1} {2}'.format(TABLE, name, sql_type)
            print('  + ' + stmt)
            db.session.execute(text(stmt))
            added_cols.append(name)

        db.session.commit()

        added_idx = []
        for idx_name, cols in NEW_INDEXES:
            if idx_name in existing_idx:
                print('  - index {0} already exists, skip'.format(idx_name))
                continue
            stmt = 'CREATE INDEX {0} ON {1} ({2})'.format(idx_name, TABLE, ', '.join(cols))
            print('  + ' + stmt)
            db.session.execute(text(stmt))
            added_idx.append(idx_name)

        db.session.commit()

        print()
        print('Added {0} columns: {1}'.format(len(added_cols), added_cols))
        print('Added {0} indexes: {1}'.format(len(added_idx), added_idx))
        return 0


if __name__ == '__main__':
    sys.exit(migrate())
