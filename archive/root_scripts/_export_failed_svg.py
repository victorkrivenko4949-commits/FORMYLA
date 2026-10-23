# -*- coding: utf-8 -*-
"""Экспорт base-SVG из failed-джобов 12 задач (svg_path сохраняется при _fail_job)."""
import io, sys, os, json, glob, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

DB = 'instance/formyla.db'
OUT = 'scripts/batch/out'
SVG = os.path.join(OUT, 'svg_ready')

svg = set(os.path.basename(f).replace('.svg', '') for f in glob.glob(os.path.join(SVG, '*.svg')))
sf = [json.loads(l) for l in open(os.path.join(OUT, 'sample_full.jsonl'), encoding='utf-8') if l.strip()]

missing = []
for r in sf:
    tid = str(r.get('task_id'))
    if f"{tid}_{r.get('grade')}" in svg:
        continue
    if any(b == tid or b.startswith(tid + '_') for b in svg):
        continue
    missing.append(r)

c = sqlite3.connect(DB, timeout=30)
c.execute('PRAGMA busy_timeout=30000')

exported = 0
for r in missing:
    tid = str(r.get('task_id'))
    grade = r.get('grade')
    cond = (r.get('condition') or '').strip()
    # ищем ЛЮБОЙ job с непустым svg_path (done или failed), последний
    row = c.execute(
        "SELECT status, svg_path FROM figure_build_jobs WHERE problem_text=? AND svg_path IS NOT NULL AND svg_path != '' "
        "ORDER BY id DESC LIMIT 1", (cond,)).fetchone()
    if not row:
        out.write('NO SVG: %s\n' % tid)
        continue
    status, svg_path = row
    content = svg_path
    if not content.lstrip().startswith('<?xml'):
        try:
            content = open(content, encoding='utf-8').read()
        except OSError:
            content = None
    if content:
        fname = '%s_%s.svg' % (tid, grade)
        with open(os.path.join(SVG, fname), 'w', encoding='utf-8') as f:
            f.write(content)
        exported += 1
        out.write('EXPORTED (%s): %s -> %s\n' % (status, tid, fname))
    else:
        out.write('EMPTY SVG: %s (status=%s)\n' % (tid, status))

c.close()
out.write('exported=%d\n' % exported)
open('_export_failed_svg.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
