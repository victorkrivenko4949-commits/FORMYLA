# -*- coding: utf-8 -*-
"""Шаг 3: слить старые 23 + новые 104 секрета в secrets_dump.json
и загрузить в БД (через utils.seed_secrets_utils).
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

if sys.platform == 'win32':
    import codecs
    try:
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    except Exception:
        pass


EXISTING_PATH = os.path.join(ROOT, 'secrets_dump.json')
NEW_PATH = os.path.join(ROOT, 'scripts', '_new_secrets_with_content.json')
BACKUP_PATH = os.path.join(ROOT, 'secrets_dump.backup_pre_gen.json')


def main() -> int:
    if not os.path.exists(EXISTING_PATH):
        print(f'ERROR: {EXISTING_PATH} not found')
        return 2
    if not os.path.exists(NEW_PATH):
        print(f'ERROR: {NEW_PATH} not found — run gen_secret_contents.py first')
        return 2

    with open(EXISTING_PATH, 'r', encoding='utf-8') as f:
        existing = json.load(f)
    with open(NEW_PATH, 'r', encoding='utf-8') as f:
        new_items = json.load(f)

    # Бэкап старого
    if not os.path.exists(BACKUP_PATH):
        with open(BACKUP_PATH, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        print(f'Backup saved: {BACKUP_PATH}')

    # Отбираем только успешные (без __error)
    new_clean = [
        x for x in new_items
        if x.get('content') and not x.get('__error')
        and len(x.get('content', '')) >= 1500
    ]
    print(f'Existing: {len(existing)}, new (valid): {len(new_clean)}')

    # Дедупликация по title
    existing_titles = {(s.get('title') or '').strip().lower() for s in existing}
    final_new = [x for x in new_clean if x['title'].strip().lower() not in existing_titles]
    print(f'Final new after dedup: {len(final_new)}')

    merged = list(existing) + final_new
    print(f'Total in merged: {len(merged)}')

    with open(EXISTING_PATH, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f'Saved: {EXISTING_PATH} ({len(merged)} entries)')

    # Распределение
    from collections import Counter
    print('By topic:', dict(Counter(s['topic'] for s in merged)))
    print('By difficulty:', dict(Counter(s.get('difficulty_level', 0) for s in merged)))

    # Опционально: загрузить в локальную БД сразу
    try:
        from app import app, db
        from utils.seed_secrets_utils import seed_secrets_from_json, get_secrets_stats
        with app.app_context():
            print('\nSeeding into local DB...')
            res = seed_secrets_from_json(json_file=EXISTING_PATH, force=True)
            print(f'Seed result: {res}')
            stats = get_secrets_stats()
            print(f'DB stats: {stats}')
    except Exception as e:
        print(f'(local DB seed skipped: {e})')

    return 0


if __name__ == '__main__':
    sys.exit(main())
