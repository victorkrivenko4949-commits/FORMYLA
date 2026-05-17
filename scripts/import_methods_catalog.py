# -*- coding: utf-8 -*-
"""Импорт каталога 89 методов из data/olympiads/methods_catalog_89.json.

Делает upsert по `method_code` в таблице `olympiad_theory`:
    * если запись существует — обновляет метаданные (grades,
      recommended_competitions, difficulty_level, frequency_vsosh_9,
      sort_order, method_name, section, related_methods)
    * текстовые поля definition_md / main_theorems_md / ... НЕ трогаются,
      если в JSON они равны null (чтобы не затереть уже залитый
      авторский контент).

Запуск:
    python scripts/import_methods_catalog.py
    python scripts/import_methods_catalog.py path/to/methods_catalog.json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402
from models import db  # noqa: E402
from models_olympiad import TheoryBlock  # noqa: E402


DEFAULT_PATH = ROOT / 'data' / 'olympiads' / 'methods_catalog_89.json'

META_FIELDS = (
    'method_name',
    'section',
    'grades',
    'recommended_competitions',
    'difficulty_level',
    'frequency_vsosh_9',
    'sort_order',
)
TEXT_FIELDS = (
    'definition_md',
    'main_theorems_md',
    'typical_techniques_md',
    'triggers_md',
    'worked_example_md',
    'pitfalls_md',
)


def main(path: Path = DEFAULT_PATH) -> int:
    print('source:', path)
    with path.open('r', encoding='utf-8') as fh:
        items = json.load(fh)
    print('items:', len(items))

    created = updated = 0
    with app.app_context():
        for raw in items:
            code = raw.get('method_code')
            if not code:
                continue
            row = TheoryBlock.query.filter_by(method_code=code).first()
            if row is None:
                row = TheoryBlock(method_code=code)
                db.session.add(row)
                created += 1
            else:
                updated += 1

            # metadata - always overwrite (caller's source of truth)
            for k in META_FIELDS:
                if k in raw:
                    setattr(row, k, raw[k])

            # related_methods: overwrite (the JSON is the source of truth)
            if 'related_methods' in raw:
                row.related_methods = list(raw['related_methods'] or [])

            # text fields - only overwrite if non-null in JSON
            for k in TEXT_FIELDS:
                v = raw.get(k)
                if v not in (None, ''):
                    setattr(row, k, v)

        db.session.commit()

        total = TheoryBlock.query.count()
        with_meta = TheoryBlock.query.filter(
            TheoryBlock.grades.isnot(None)
        ).count()
        with_text = TheoryBlock.query.filter(
            TheoryBlock.definition_md.isnot(None)
        ).count()

    print()
    print('created:', created)
    print('updated:', updated)
    print()
    print('TOTAL methods in DB :', total)
    print('  with metadata     :', with_meta)
    print('  with full text    :', with_text)
    return 0


if __name__ == '__main__':
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    sys.exit(main(p))
