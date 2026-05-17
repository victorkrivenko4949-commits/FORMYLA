# -*- coding: utf-8 -*-
"""Domain distribution per grade in master 5345."""
import json
import sys
from collections import Counter
from pathlib import Path

SRC = Path(r'C:\Users\Victor\Downloads\formyla_master_5345_fixed_after_manual_audit.json')

# Force stdout to UTF-8 to avoid Windows cp1251 issues
sys.stdout.reconfigure(encoding='utf-8')

with SRC.open('r', encoding='utf-8') as fh:
    d = json.load(fh)

tasks = d['tasks']
print(f'Total tasks: {len(tasks)}')

by_grade = {}
for t in tasks:
    g = t.get('grade')
    dom = t.get('domain')
    by_grade.setdefault(g, Counter())[dom] += 1

for g in sorted(by_grade.keys()):
    print(f'\n=== grade {g} ({sum(by_grade[g].values())} tasks) ===')
    for dom, cnt in sorted(by_grade[g].items(), key=lambda x: -x[1]):
        print(f'  {dom!s:<45} {cnt}')

# Также проверим, сколько id уже есть в БД (пересечение с прошлым импортом).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import app
from models_grade import GradeTask

with app.app_context():
    existing = {row[0] for row in GradeTask.query.with_entities(GradeTask.source_id).all()}

src_ids = {t['id'] for t in tasks}
overlap = src_ids & existing
print(f'\n=== Overlap with grade_tasks ===')
print(f'  in DB now : {len(existing)}')
print(f'  in file   : {len(src_ids)}')
print(f'  overlap   : {len(overlap)}')
print(f'  new       : {len(src_ids - existing)}')
