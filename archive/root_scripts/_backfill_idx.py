# -*- coding: utf-8 -*-
"""Бэкфилл _idx в уже записанные результаты аудита.

Сопоставляет каждую запись в выходных файлах с индексом строки исходного
файла по контенту (task_text + correct_answer + solution), чтобы --resume
не пересоздавал уже обработанные задачи.
"""
import io, json, os

SRC = r'C:\Users\Redmi\Downloads\all_formyla_1_4_final_CORRECTED_v2 (3).jsonl'
FILES = [
    'FORMYLA_1_4_AUDIT_BOTH_CORRECT.jsonl',
    'FORMYLA_1_4_AUDIT_BOTH_INCORRECT.jsonl',
    'FORMYLA_1_4_AUDIT_DISPUTED.jsonl',
    'FORMYLA_1_4_AUDIT_ERROR.jsonl',
]

# 1. Загрузить исходные задачи с индексами
src_rows = []
with io.open(SRC, encoding='utf-8') as f:
    for idx, line in enumerate(f):
        line = line.strip()
        if not line:
            continue
        try:
            t = json.loads(line)
        except json.JSONDecodeError:
            continue
        sig = (t.get('task_text') or '', t.get('correct_answer') or '', t.get('solution') or '')
        src_rows.append((idx, sig))

# Индекс по сигнатуре -> список незанятых индексов
from collections import defaultdict
by_sig = defaultdict(list)
for idx, sig in src_rows:
    by_sig[sig].append(idx)

# 2. Для каждого выходного файла — перезаписать с добавленным _idx
report = io.open('_backfill_report.txt', 'w', encoding='utf-8')
claimed = set()

for path in FILES:
    if not os.path.exists(path):
        report.write(path + ' MISSING\n')
        continue
    rows = []
    with io.open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    out_rows = []
    matched = 0
    for r in rows:
        if r.get('_idx') is not None:
            out_rows.append(r)
            matched += 1
            continue
        t = r.get('task') or {}
        sig = (t.get('task_text') or '', t.get('correct_answer') or '', t.get('solution') or '')
        cands = by_sig.get(sig, [])
        assigned = None
        for c in cands:
            if c not in claimed:
                assigned = c
                break
        if assigned is not None:
            claimed.add(assigned)
            r['_idx'] = assigned
            matched += 1
        out_rows.append(r)

    with io.open(path, 'w', encoding='utf-8') as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    report.write('%s rows=%d matched=%d\n' % (path, len(out_rows), matched))

report.write('TOTAL claimed=%d\n' % len(claimed))
report.close()
print('backfill done')
