# -*- coding: utf-8 -*-
"""Инспектировать формат formyla_master_5345_fixed_after_manual_audit.json."""
import json
from collections import Counter
from pathlib import Path

SRC = Path(r'C:\Users\Victor\Downloads\formyla_master_5345_fixed_after_manual_audit.json')

with SRC.open('r', encoding='utf-8') as fh:
    d = json.load(fh)

print('Top keys :', list(d.keys()))
print('Dataset  :', d.get('dataset_name'))
print('Version  :', d.get('version'))
print('Total    :', d.get('total_tasks'))

tasks = d.get('tasks') or []
print('Tasks    :', len(tasks))

if tasks:
    first = tasks[0]
    print()
    print('--- First task keys ---')
    for k in first.keys():
        v = first[k]
        if isinstance(v, str):
            preview = v[:80].replace('\n', ' ')
            print(f'  {k:<20} (str, len={len(v)}): {preview!r}')
        elif isinstance(v, (list, dict)):
            print(f'  {k:<20} ({type(v).__name__}, len={len(v)}): {str(v)[:120]}')
        else:
            print(f'  {k:<20} ({type(v).__name__}): {v}')

    # Распределение по классам / темам / уровням, если поля есть
    for fld in ('grade', 'class', 'level', 'difficulty', 'topic', 'domain', 'subject'):
        vals = [t.get(fld) for t in tasks if fld in t]
        if vals:
            c = Counter(vals)
            print()
            print(f'--- {fld} distribution ({len(c)} unique) ---')
            for k, n in sorted(c.items(), key=lambda x: (str(x[0]))):
                print(f'  {str(k):<30} {n}')
