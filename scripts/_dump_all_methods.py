# -*- coding: utf-8 -*-
"""Дамп ВСЕХ методов из локальной БД в JSON (каталог для прода).

Читает таблицу olympiad_theory (модель TheoryBlock) и сохраняет
в data/olympiads/methods_catalog_105.json в том же формате,
что и существующий methods_catalog_89.json.

Запуск:
    python scripts/_dump_all_methods.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402
from models import db  # noqa: E402
from models_olympiad import TheoryBlock  # noqa: E402

EXPORT_FIELDS = (
    'method_code',
    'method_name',
    'section',
    'grades',
    'recommended_competitions',
    'difficulty_level',
    'frequency_vsosh_9',
    'total_count',
    'share_percent',
    'sort_order',
    'definition_md',
    'main_theorems_md',
    'typical_techniques_md',
    'triggers_md',
    'worked_example_md',
    'pitfalls_md',
    'why_it_works_md',
    'signal_phrases',
    'first_moves',
    'prerequisites',
    'leads_to',
    'related_methods',
)

OUT_PATH = ROOT / 'data' / 'olympiads' / 'methods_catalog_105.json'


def row_to_dict(row: TheoryBlock) -> dict:
    d = {}
    for k in EXPORT_FIELDS:
        v = getattr(row, k, None)
        if v is not None:
            d[k] = v
    return d


def main() -> int:
    issues: list[str] = []

    with app.app_context():
        rows: list[TheoryBlock] = TheoryBlock.query.order_by(
            TheoryBlock.section,
            TheoryBlock.sort_order,
            TheoryBlock.method_code,
        ).all()

        total = len(rows)
        print(f'Total records in olympiad_theory: {total}')

        # ── Проверка методов без названия ──
        bad_methods = []
        for r in rows:
            name = (r.method_name or '').strip()
            if not name or name in ('—', '–', '-', ''):
                bad_methods.append((r.method_code, r.method_name, 'empty_name'))
            elif name == r.method_code:
                bad_methods.append((r.method_code, r.method_name, 'name_equals_code'))
            elif len(name) < 3:
                bad_methods.append((r.method_code, r.method_name, 'too_short'))

        if bad_methods:
            print(f'\n⚠  WARNING: {len(bad_methods)} methods with missing/invalid names:')
            for code, name, reason in bad_methods:
                print(f'   {code}: name={name!r} ({reason})')
                issues.append(f'{code}: name={name!r} ({reason})')
        else:
            print('\n✅ All methods have valid names.')

        # ── Проверка definition_md ──
        no_def = [r for r in rows if not (r.definition_md or '').strip()]
        if no_def:
            print(f'\n⚠  WARNING: {len(no_def)} methods without definition_md:')
            for r in no_def:
                print(f'   {r.method_code}: {r.method_name}')
                issues.append(f'{r.method_code}: missing definition_md')
        else:
            print('\n✅ All methods have definition_md.')

        # ── Сбор данных ──
        data = [row_to_dict(r) for r in rows]

    # ── Запись JSON ──
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f'\nWritten: {OUT_PATH} ({len(data)} methods)')

    if issues:
        print(f'\n⚠  {len(issues)} issue(s) found — review before pushing:')
        for i in issues:
            print(f'   • {i}')
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
