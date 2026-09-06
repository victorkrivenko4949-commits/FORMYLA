# -*- coding: utf-8 -*-
import io, sys, os, json, sqlite3, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

OUT = 'scripts/batch/out'
DB = 'instance/formyla.db'

# file2 missing conditions
missing = [json.loads(l) for l in open(os.path.join(OUT, 'sample_file2_missing.jsonl'), encoding='utf-8') if l.strip()]
conds = [(r.get('condition') or '').strip() for r in missing]

c = sqlite3.connect(DB, timeout=30)
c.execute('PRAGMA busy_timeout=30000')

done = 0
failed = 0
active = 0
for cond in conds:
    row = c.execute("SELECT status FROM figure_build_jobs WHERE problem_text=? ORDER BY id DESC LIMIT 1", (cond,)).fetchone()
    if row is None:
        continue
    if row[0] == 'done':
        done += 1
    elif row[0] == 'failed':
        failed += 1
    else:
        active += 1

out.write('file2 missing (380): done=%d failed=%d active/queued=%d\n' % (done, failed, active))

# geometry missing
sf = [json.loads(l) for l in open(os.path.join(OUT, 'sample_full.jsonl'), encoding='utf-8') if l.strip()]
import glob
svg = set(os.path.basename(f).replace('.svg', '') for f in glob.glob(os.path.join(OUT, 'svg_ready', '*.svg')))
geo_missing = []
for r in sf:
    tid = str(r.get('task_id'))
    if f"{tid}_{r.get('grade')}" in svg or any(b == tid or b.startswith(tid + '_') for b in svg):
        continue
    geo_missing.append(tid)
out.write('geometry missing: %d -> %s\n' % (len(geo_missing), geo_missing))

c.close()
open('_progress_db.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
