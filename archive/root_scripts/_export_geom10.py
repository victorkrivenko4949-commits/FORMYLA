# -*- coding: utf-8 -*-
"""Выгрузить 10 упорных geometry-задач в читаемый файл + JSONL."""
import io, sys, os, json, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUT = 'scripts/batch/out'
SVG = os.path.join(OUT, 'svg_ready')

svg = set(os.path.basename(f).replace('.svg', '') for f in glob.glob(os.path.join(SVG, '*.svg')))
sf = [json.loads(l) for l in open(os.path.join(OUT, 'sample_full.jsonl'), encoding='utf-8') if l.strip()]

missing = []
for r in sf:
    tid = str(r.get('task_id'))
    if f"{tid}_{r.get('grade')}" in svg or any(b == tid or b.startswith(tid + '_') for b in svg):
        continue
    missing.append(r)

# JSONL
with open('geometry_10_remaining.jsonl', 'w', encoding='utf-8') as f:
    for r in missing:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

# Читаемый txt
lines = []
for i, r in enumerate(missing, 1):
    lines.append('=' * 70)
    lines.append('ЗАДАЧА %d' % i)
    lines.append('task_id: %s' % r.get('task_id'))
    lines.append('класс: %s' % r.get('grade'))
    lines.append('уровень: %s' % r.get('level'))
    lines.append('--- УСЛОВИЕ ---')
    lines.append(r.get('condition') or '')
    lines.append('--- РЕШЕНИЕ ---')
    lines.append(r.get('solution') or '(нет)')
    lines.append('--- ОТВЕТ ---')
    lines.append(str(r.get('answer')) or '(нет)')
    lines.append('')

txt = '\n'.join(lines)
with open('geometry_10_remaining.txt', 'w', encoding='utf-8') as f:
    f.write(txt)

print('exported %d tasks' % len(missing))
print('JSONL: geometry_10_remaining.jsonl')
print('TXT:   geometry_10_remaining.txt')
