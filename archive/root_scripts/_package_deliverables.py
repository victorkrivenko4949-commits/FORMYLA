# -*- coding: utf-8 -*-
"""Упаковать готовые чертежи в zip-архивы.

1) geometry_7_11_drawings.zip   — чертежи датасета geometry 7-11 (362 задачи).
2) file2_waves_1_3_drawings.zip — чертежи волн 1-3 датасета file2 (2187 задач).
"""
import io, sys, os, json, glob, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUT = os.path.join('scripts', 'batch', 'out')
SVG = os.path.join(OUT, 'svg_ready')
DELIV = '_deliverables'
os.makedirs(DELIV, exist_ok=True)

svg_map = {os.path.basename(f): f for f in glob.glob(os.path.join(SVG, '*.svg'))}

def load_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    for l in open(path, encoding='utf-8'):
        l = l.strip()
        if not l:
            continue
        try:
            r = json.loads(l)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict):
            rows.append(r)
    return rows

# ── 1. Geometry 7-11 ────────────────────────────────────────────────────────
sf = load_jsonl(os.path.join(OUT, 'sample_full.jsonl'))
geo_found = []
geo_missing = []
for r in sf:
    tid = str(r.get('task_id'))
    grade = r.get('grade')
    cand = f"{tid}_{grade}.svg"
    if cand in svg_map:
        geo_found.append((tid, svg_map[cand]))
    else:
        matches = [f for f in svg_map if f.startswith(tid + '_')]
        if matches:
            geo_found.append((tid, os.path.join(SVG, matches[0])))
        else:
            geo_missing.append(tid)

geo_zip = os.path.join(DELIV, 'geometry_7_11_drawings.zip')
with zipfile.ZipFile(geo_zip, 'w', zipfile.ZIP_DEFLATED) as z:
    for tid, path in geo_found:
        z.write(path, os.path.basename(path))

# ── 2. file2 waves 1-3 ──────────────────────────────────────────────────────
w123 = set()
for w in (1, 2, 3):
    p = os.path.join(OUT, f'sample_file2_wave{w}.jsonl')
    for r in load_jsonl(p):
        w123.add(str(r.get('task_id')))

f2_found = []
for f in glob.glob(os.path.join(SVG, 'f2_*.svg')):
    b = os.path.basename(f)[:-4]          # f2_<idx>_<grade>
    tid = b.rsplit('_', 1)[0]             # f2_<idx>
    if tid in w123:
        f2_found.append(f)

f2_zip = os.path.join(DELIV, 'file2_waves_1_3_drawings.zip')
with zipfile.ZipFile(f2_zip, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in sorted(f2_found):
        z.write(f, os.path.basename(f))

summary = (
    "geometry dataset: %d tasks; packaged SVG=%d; missing=%d\n" % (len(sf), len(geo_found), len(geo_missing))
    + "  missing: %s\n" % geo_missing
    + "  zip: %s (%d bytes)\n" % (geo_zip, os.path.getsize(geo_zip))
    + "file2 waves1-3 tasks: %d; packaged SVG=%d\n" % (len(w123), len(f2_found))
    + "  zip: %s (%d bytes)\n" % (f2_zip, os.path.getsize(f2_zip))
)
open(os.path.join(DELIV, '_summary.txt'), 'w', encoding='utf-8').write(summary)
print(summary)
