# -*- coding: utf-8 -*-
"""Экспортировать готовые file2-чертежи (done) в svg_ready и пересобрать архив."""
import io, sys, os, json, glob, sqlite3, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

DB = 'instance/formyla.db'
OUT = 'scripts/batch/out'
SVG = os.path.join(OUT, 'svg_ready')
DELIV = '_deliverables'
os.makedirs(SVG, exist_ok=True)
os.makedirs(DELIV, exist_ok=True)

# маппинг job_id -> task_id/grade из всех results.jsonl
results = {}
for rp in [os.path.join(OUT, 'results.jsonl'),
           os.path.join(OUT, 'wave4_retry_out', 'results.jsonl'),
           os.path.join(OUT, 'file2_missing_out', 'results.jsonl'),
           os.path.join(OUT, 'file2_full_out', 'results.jsonl')]:
    if os.path.exists(rp):
        for l in io.open(rp, encoding='utf-8'):
            l = l.strip()
            if not l:
                continue
            try:
                r = json.loads(l)
            except json.JSONDecodeError:
                continue
            results[r.get('job_id')] = r

c = sqlite3.connect(DB, timeout=30)
c.execute('PRAGMA busy_timeout=30000')

# все done-джобы user 1301
rows = c.execute("SELECT id, svg_path FROM figure_build_jobs WHERE user_id=1301 AND status='done' AND svg_path IS NOT NULL AND svg_path != ''").fetchall()
exported = 0
for jid, svg_path in rows:
    r = results.get(jid, {})
    tid = r.get('task_id')
    if not tid:
        continue
    content = svg_path
    if not content.lstrip().startswith('<?xml'):
        try:
            content = io.open(content, encoding='utf-8').read()
        except OSError:
            continue
    grade = r.get('grade', '')
    fname = '%s_%s.svg' % (tid, grade if grade is not None else '')
    with io.open(os.path.join(SVG, fname), 'w', encoding='utf-8') as f:
        f.write(content)
    exported += 1
c.close()
out.write('exported done SVGs: %d\n' % exported)

# ── пересчитать file2 coverage ──
sample = [json.loads(l) for l in io.open(os.path.join(OUT, 'sample_file2.jsonl'), encoding='utf-8') if l.strip()]
svg = set(os.path.basename(f).replace('.svg', '') for f in glob.glob(os.path.join(SVG, 'f2_*.svg')))
have = sum(1 for r in sample if str(r.get('task_id')) in svg)
out.write('file2 coverage: %d / %d (missing=%d)\n' % (have, len(sample), len(sample) - have))

# ── пересобрать file2 архив ──
f2_svg = glob.glob(os.path.join(SVG, 'f2_*.svg'))
with zipfile.ZipFile(os.path.join(DELIV, 'file2_all_waves_drawings.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
    for f in sorted(f2_svg):
        z.write(f, os.path.basename(f))
out.write('file2 zip rebuilt: %d svg\n' % len(f2_svg))

open('_export_file2_done.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
