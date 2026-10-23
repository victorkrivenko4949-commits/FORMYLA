# -*- coding: utf-8 -*-
import io, sys, os, json, glob, sqlite3, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

OUT = 'scripts/batch/out'
DB = 'instance/formyla.db'
SVG = os.path.join(OUT, 'svg_ready')

# ── file2 MISSING run ──
d = os.path.join(OUT, 'file2_missing_out')
res = os.path.join(d, 'results.jsonl')
total = 380
done = failed = timeout = 0
n = 0
if os.path.exists(res):
    rows = [json.loads(l) for l in open(res, encoding='utf-8') if l.strip()]
    n = len(rows)
    done = sum(1 for r in rows if r.get('status') == 'done')
    failed = sum(1 for r in rows if r.get('status') == 'failed')
    timeout = sum(1 for r in rows if r.get('status') == 'timeout')
out.write('FILE2 missing: total=%d done=%d failed=%d timeout=%d remaining=%d\n'
          % (total, done, failed, timeout, total - n))

# ── geometry ──
sf = [json.loads(l) for l in open(os.path.join(OUT, 'sample_full.jsonl'), encoding='utf-8') if l.strip()]
svg = set(os.path.basename(f).replace('.svg', '') for f in glob.glob(os.path.join(SVG, '*.svg')))
have = 0
missing = []
for r in sf:
    tid = str(r.get('task_id'))
    if f"{tid}_{r.get('grade')}" in svg or any(b == tid or b.startswith(tid + '_') for b in svg):
        have += 1
    else:
        missing.append(tid)
out.write('GEOMETRY: %d/362 (missing=%d)\n' % (have, len(missing)))

# ── DB ──
c = sqlite3.connect(DB, timeout=30)
out.write('DB active: %s\n' % dict(collections.Counter(r[0] for r in c.execute(
    "SELECT status FROM figure_build_jobs WHERE status NOT IN ('done','failed')"))))
# total done today
out.write('DB done total: %d, failed total: %d\n' % (
    c.execute("SELECT COUNT(*) FROM figure_build_jobs WHERE status='done'").fetchone()[0],
    c.execute("SELECT COUNT(*) FROM figure_build_jobs WHERE status='failed'").fetchone()[0]))
c.close()

open('_monitor2.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
