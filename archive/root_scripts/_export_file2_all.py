# -*- coding: utf-8 -*-
"""Собрать: 1) условия всех 2187 file2-задач; 2) папку с готовыми чертежами."""
import io, sys, os, json, glob, shutil
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUT = 'scripts/batch/out'
SVG = os.path.join(OUT, 'svg_ready')

sample = [json.loads(l) for l in io.open(os.path.join(OUT, 'sample_file2.jsonl'), encoding='utf-8') if l.strip()]

# ── 1. условия всех 2187 ──
lines = []
for i, r in enumerate(sample, 1):
    lines.append('=' * 70)
    lines.append('ЗАДАЧА %d' % i)
    lines.append('task_id: %s' % r.get('task_id'))
    lines.append('класс: %s | уровень: %s' % (r.get('grade'), r.get('level')))
    lines.append('--- УСЛОВИЕ ---')
    lines.append(r.get('condition') or '')
    lines.append('--- ОТВЕТ ---')
    lines.append(str(r.get('answer')) or '(нет)')
    lines.append('')

txt = '\n'.join(lines)
with io.open('file2_2187_conditions.txt', 'w', encoding='utf-8') as f:
    f.write(txt)

with io.open('file2_2187_conditions.jsonl', 'w', encoding='utf-8') as f:
    for r in sample:
        f.write(json.dumps({
            'task_id': r.get('task_id'),
            'grade': r.get('grade'),
            'level': r.get('level'),
            'condition': r.get('condition'),
            'answer': r.get('answer'),
            'solution': r.get('solution'),
        }, ensure_ascii=False) + '\n')

# ── 2. папка с готовыми чертежами ──
have = set()
for f in glob.glob(os.path.join(SVG, 'f2_*.svg')):
    have.add(os.path.basename(f)[:-4].rsplit('_', 1)[0])

DEST = '_deliverables/file2_drawings'
os.makedirs(DEST, exist_ok=True)
copied = 0
for r in sample:
    tid = str(r.get('task_id'))
    if tid not in have:
        continue
    # найти svg по точному имени
    for f in glob.glob(os.path.join(SVG, tid + '_*.svg')):
        shutil.copy2(f, os.path.join(DEST, os.path.basename(f)))
        copied += 1

print('file2 total tasks: %d' % len(sample))
print('have drawings: %d' % len(have))
print('copied svg files: %d' % copied)
print('TXT: file2_2187_conditions.txt')
print('JSONL: file2_2187_conditions.jsonl')
print('FOLDER: %s' % DEST)
