# -*- coding: utf-8 -*-
import io, sys, os, json, glob, collections, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

# ── wave4 retry progress ──
d = 'scripts/batch/out/wave4_retry_out'
total = 334
done = failed = timeout = 0
res_path = os.path.join(d, 'results.jsonl')
if os.path.exists(res_path):
    rows = [json.loads(l) for l in open(res_path, encoding='utf-8') if l.strip()]
    done = sum(1 for r in rows if r.get('status') == 'done')
    failed = sum(1 for r in rows if r.get('status') == 'failed')
    timeout = sum(1 for r in rows if r.get('status') == 'timeout')
    out.write('wave4_retry: total=%d, done=%d, failed=%d, timeout=%d, remaining=%d\n'
              % (total, done, failed, timeout, total - len(rows)))

# ── geometry 7-11 completeness ──
svg_map = {os.path.basename(f).replace('.svg', ''): f for f in glob.glob('scripts/batch/out/svg_ready/*.svg')}
sf = [json.loads(l) for l in open('scripts/batch/out/sample_full.jsonl', encoding='utf-8') if l.strip()]
missing = []
for r in sf:
    tid = str(r.get('task_id'))
    grade = r.get('grade')
    if f"{tid}_{grade}" in svg_map:
        continue
    if any(b == tid or b.startswith(tid + '_') for b in svg_map):
        continue
    missing.append(tid)
out.write('geometry: total=%d, have_svg=%d, missing=%d\n' % (len(sf), len(sf) - len(missing), len(missing)))
if missing:
    out.write('missing ids:\n')
    for m in missing:
        out.write('  ' + m + '\n')

# ── DB: active jobs for current run ──
import sqlite3
c = sqlite3.connect('instance/formyla.db')
out.write('DB figure_build_jobs active (not final): %s\n' % dict(collections.Counter(
    r[0] for r in c.execute("SELECT status FROM figure_build_jobs WHERE status NOT IN ('done','failed')"))))
c.close()

open('_poll.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
