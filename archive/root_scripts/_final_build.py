# -*- coding: utf-8 -*-
"""Финальная сборка: экспорт волны 4 + пересборка архивов."""
import io, sys, os, json, glob, sqlite3, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

DB = 'instance/formyla.db'
OUT = 'scripts/batch/out'
SVG = os.path.join(OUT, 'svg_ready')
DELIV = '_deliverables'
os.makedirs(SVG, exist_ok=True)
os.makedirs(DELIV, exist_ok=True)

c = sqlite3.connect(DB, timeout=30)
c.execute('PRAGMA busy_timeout=30000')

# ── 1. Экспортировать ВСЕ done-джобы user 1301 в svg_ready ──
# Маппинг job_id -> task_id/grade из обоих results.jsonl
results = {}
for rp in [os.path.join(OUT, 'results.jsonl'), os.path.join(OUT, 'wave4_retry_out', 'results.jsonl')]:
    if os.path.exists(rp):
        for l in open(rp, encoding='utf-8'):
            l = l.strip()
            if not l:
                continue
            try:
                r = json.loads(l)
            except json.JSONDecodeError:
                continue
            results[r.get('job_id')] = r

rows = c.execute("SELECT id, svg_path, status FROM figure_build_jobs WHERE user_id=1301 AND status='done'").fetchall()
exported = 0
for jid, svg_path, status in rows:
    if not svg_path:
        continue
    r = results.get(jid, {})
    tid = r.get('task_id')
    grade = r.get('grade')
    if not tid:
        continue
    content = svg_path
    if not content.lstrip().startswith('<?xml'):
        try:
            content = open(content, encoding='utf-8').read()
        except OSError:
            continue
    fname = '%s_%s.svg' % (tid, grade if grade is not None else '')
    with open(os.path.join(SVG, fname), 'w', encoding='utf-8') as f:
        f.write(content)
    exported += 1
out.write('exported done SVGs to svg_ready: %d\n' % exported)

# ── 2. Geometry zip ──
sf = [json.loads(l) for l in open(os.path.join(OUT, 'sample_full.jsonl'), encoding='utf-8') if l.strip()]
svg_files = {os.path.basename(f): f for f in glob.glob(os.path.join(SVG, '*.svg'))}
geo_found = 0
geo_missing = []
with zipfile.ZipFile(os.path.join(DELIV, 'geometry_7_11_drawings.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
    for r in sf:
        tid = str(r.get('task_id'))
        grade = r.get('grade')
        cand = '%s_%s.svg' % (tid, grade)
        if cand in svg_files:
            z.write(svg_files[cand], cand)
            geo_found += 1
        else:
            m = [f for f in svg_files if f.startswith(tid + '_')]
            if m:
                z.write(svg_files[m[0]], m[0])
                geo_found += 1
            else:
                geo_missing.append(tid)
out.write('geometry zip: %d / %d (missing=%d)\n' % (geo_found, len(sf), len(geo_missing)))
out.write('missing: %s\n' % geo_missing)

# ── 3. file2 waves 1-4 zip (всё f2_) ──
f2_svg = [f for f in glob.glob(os.path.join(SVG, 'f2_*.svg'))]
with zipfile.ZipFile(os.path.join(DELIV, 'file2_all_waves_drawings.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
    for f in sorted(f2_svg):
        z.write(f, os.path.basename(f))
out.write('file2 all-waves zip: %d svg\n' % len(f2_svg))

# ── 4. wave4-only zip ──
w4 = set()
for w in (4,):
    p = os.path.join(OUT, 'sample_file2_wave%d.jsonl' % w)
    if os.path.exists(p):
        for l in open(p, encoding='utf-8'):
            l = l.strip()
            if l:
                try:
                    w4.add(json.loads(l)['task_id'])
                except Exception:
                    pass
w4_svg = [f for f in f2_svg if os.path.basename(f)[:-4].rsplit('_', 1)[0] in w4]
with zipfile.ZipFile(os.path.join(DELIV, 'file2_wave4_drawings.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
    for f in sorted(w4_svg):
        z.write(f, os.path.basename(f))
out.write('file2 wave4 zip: %d svg\n' % len(w4_svg))

c.close()
open('_final_build.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
