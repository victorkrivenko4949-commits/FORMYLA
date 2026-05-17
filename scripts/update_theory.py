# -*- coding: utf-8 -*-
"""Применить файл с текстами теории к таблице olympiad_theory.

Формат входного JSON (массив):
    [
      {
        "method_code": "E14",
        "definition_md": "...",
        "main_theorems_md": "...",
        "typical_techniques_md": "...",
        "triggers_md": "...",
        "worked_example_md": "...",
        "pitfalls_md": "...",
        "related_methods": ["E14a", "E14b", "E4"]
      },
      ...
    ]

Правила:
    * UPDATE по `method_code`. Если метода нет в БД — печатается
      предупреждение, метод пропускается (не падаем).
    * Текстовые поля _md перезаписываются ТОЛЬКО если в JSON
      значение НЕ null/пусто. Это позволяет присылать частичные
      обновления (например, только worked_example_md).
    * `related_methods` перезаписывается полностью, если ключ
      присутствует в объекте. Чтобы не трогать — не присылайте ключ.
    * Поле `method_name` опционально и тоже перезаписывается, если
      есть в JSON.

Запуск:
    python scripts/update_theory.py data/olympiads/theory_content_batch_1.json
    python scripts/update_theory.py path/to/file.json [path/to/file2.json ...]

    # авто-выбор всех файлов theory_content_batch_*.json в data/olympiads:
    python scripts/update_theory.py
"""

from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402
from models import db  # noqa: E402
from models_olympiad import TheoryBlock  # noqa: E402


TEXT_FIELDS = (
    'definition_md',
    'main_theorems_md',
    'typical_techniques_md',
    'triggers_md',
    'worked_example_md',
    'pitfalls_md',
)
OPTIONAL_META = ('method_name', 'section')

DEFAULT_DIR = ROOT / 'data' / 'olympiads'


def pick_paths(argv):
    if len(argv) > 1:
        return [Path(p) for p in argv[1:]]
    matches = sorted(glob.glob(str(DEFAULT_DIR / 'theory_content_batch_*.json')))
    if not matches:
        print('ERROR: no theory_content_batch_*.json found in', DEFAULT_DIR)
        sys.exit(1)
    return [Path(p) for p in matches]


def apply_file(path: Path):
    print('=== file:', path.relative_to(ROOT) if path.is_absolute() and ROOT in path.parents else path)
    if not path.is_file():
        print('  ERROR: file not found, skip')
        return 0, 0, []
    with path.open('r', encoding='utf-8') as fh:
        items = json.load(fh)
    if not isinstance(items, list):
        print('  ERROR: top-level JSON must be a list, got', type(items).__name__)
        return 0, 0, []
    print('  items in file:', len(items))

    updated = 0
    missing = 0
    missing_codes = []
    touched_codes = []
    for raw in items:
        code = raw.get('method_code')
        if not code:
            print('  WARN: item without method_code, skip')
            continue
        row = TheoryBlock.query.filter_by(method_code=code).first()
        if row is None:
            missing += 1
            missing_codes.append(code)
            continue

        changed = []
        # Optional metadata (rare).
        for k in OPTIONAL_META:
            if k in raw and raw[k] not in (None, ''):
                if getattr(row, k) != raw[k]:
                    setattr(row, k, raw[k])
                    changed.append(k)

        # Text fields - overwrite only if non-null in JSON.
        for k in TEXT_FIELDS:
            if k in raw and raw[k] not in (None, ''):
                if getattr(row, k) != raw[k]:
                    setattr(row, k, raw[k])
                    changed.append(k)

        # related_methods - overwrite if key present (even if empty list).
        if 'related_methods' in raw:
            new_list = list(raw['related_methods'] or [])
            if (row.related_methods or []) != new_list:
                row.related_methods = new_list
                changed.append('related_methods')

        if changed:
            updated += 1
            touched_codes.append((code, changed))

    db.session.commit()

    print('  updated rows:', updated)
    print('  missing in DB:', missing)
    if missing_codes:
        print('    -', ', '.join(missing_codes))
    if touched_codes:
        for code, ch in touched_codes:
            print('  + {0}: {1}'.format(code, ', '.join(ch)))
    return updated, missing, missing_codes


def main():
    paths = pick_paths(sys.argv)
    total_updated = 0
    total_missing = 0
    all_missing = []
    with app.app_context():
        for p in paths:
            u, m, mc = apply_file(p)
            total_updated += u
            total_missing += m
            all_missing.extend(mc)

        # Final DB stats.
        total = TheoryBlock.query.count()
        with_text = TheoryBlock.query.filter(
            TheoryBlock.definition_md.isnot(None)
        ).count()

    print()
    print('====== SUMMARY ======')
    print('files processed         :', len(paths))
    print('rows updated (total)    :', total_updated)
    print('rows missing in DB      :', total_missing)
    if all_missing:
        print('missing codes           :', ', '.join(all_missing))
    print()
    print('TheoryBlock in DB       :', total)
    print('  with definition_md    :', with_text)
    print('  without (placeholder) :', total - with_text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
