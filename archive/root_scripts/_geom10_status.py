# -*- coding: utf-8 -*-
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
    if f"{tid}_{r.get('grade')}" in svg or any(b == tid or b.startswith(tid + '_') for b in svg):
        continue
    missing.append(r)

c = sqlite3.connect(DB, timeout=30)
c.execute('PRAGMA busy_timeout=30000')

for r in missing:
    tid = str(r.get('task_id'))
    cond = (r.get('condition') or '').strip()
    row = c.execute("SELECT id, status, error, svg_path FROM figure_build_jobs WHERE problem_text=? ORDER BY id DESC LIMIT 1", (cond,)).fetchone()
    if row is None:
        out.write('%-55s NO JOB\n' % tid)
    else:
        out.write('%-55s job=%d status=%-14s svg=%s error=%s\n'
                  % (tid, row[0], row[1], 'Y' if row[3] else 'N', (row[2] or '')[:70]))
c.close()
open('_geom10_status.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
