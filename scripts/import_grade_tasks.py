# -*- coding: utf-8 -*-
"""Импорт 1600 задач 5–6 классов из data/olympiads/grade_5_6_tasks.json.

Делает upsert по source_id (например 'math_g5_natural_numbers_l1_t0001').

Запуск:
    python scripts/import_grade_tasks.py
    python scripts/import_grade_tasks.py path/to/file.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402
from models import db  # noqa: E402
from models_grade import GradeTask, GRADE_DOMAINS  # noqa: E402


DEFAULT_PATH = ROOT / 'data' / 'olympiads' / 'grade_5_6_tasks.json'

ALLOWED_DOMAINS = set()
for ds in GRADE_DOMAINS.values():
    ALLOWED_DOMAINS.update(ds)


def main(path: Path = DEFAULT_PATH) -> int:
    print('source:', path)
    with path.open('r', encoding='utf-8') as fh:
        payload = json.load(fh)

    if isinstance(payload, dict) and 'tasks' in payload:
        items = payload['tasks']
    elif isinstance(payload, list):
        items = payload
    else:
        print('ERROR: expected dict with "tasks" key or top-level list')
        return 1
    print('items in file:', len(items))

    created = updated = skipped = 0
    skipped_reasons = Counter()
    by_grade = Counter()
    by_domain = Counter()

    with app.app_context():
        for raw in items:
            sid = raw.get('id')
            grade = raw.get('grade')
            domain = raw.get('domain')
            if not sid:
                skipped += 1
                skipped_reasons['no_id'] += 1
                continue
            if grade not in (5, 6):
                skipped += 1
                skipped_reasons['bad_grade'] += 1
                continue
            if domain not in GRADE_DOMAINS.get(grade, ()):
                skipped += 1
                skipped_reasons['domain_not_in_grade'] += 1
                continue
            statement = raw.get('statement')
            if not statement:
                skipped += 1
                skipped_reasons['no_statement'] += 1
                continue

            row = GradeTask.query.filter_by(source_id=sid).first()
            if row is None:
                row = GradeTask(source_id=sid)
                db.session.add(row)
                created += 1
            else:
                updated += 1

            row.grade = grade
            row.domain = domain
            row.subject = raw.get('subject') or 'math'
            row.level = raw.get('level')
            row.topic = raw.get('topic')
            row.statement = statement
            row.answer = raw.get('answer')
            row.solution = raw.get('solution')
            row.status = raw.get('status')
            row.tags = raw.get('tags') or []

            by_grade[grade] += 1
            by_domain[(grade, domain)] += 1

        db.session.commit()
        total_in_db = GradeTask.query.count()

    print()
    print('created:', created)
    print('updated:', updated)
    print('skipped:', skipped, dict(skipped_reasons))
    print()
    print('TOTAL by grade:')
    for g in sorted(by_grade):
        print(f'  grade {g}: {by_grade[g]}')
    print()
    print('TOTAL by (grade, domain):')
    for (g, d), n in sorted(by_domain.items()):
        print(f'  {g}/{d}: {n}')
    print()
    print('TOTAL rows in grade_tasks:', total_in_db)
    return 0


if __name__ == '__main__':
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    sys.exit(main(p))
