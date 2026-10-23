# -*- coding: utf-8 -*-
import io, sys, os, json, glob, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

OUT = 'scripts/batch/out'
DB = 'instance/formyla.db'
SVG = os.path.join(OUT, 'svg_ready')

svg = set(os.path.basename(f).replace('.svg', '') for f in glob.glob(os.path.join(SVG, '*.svg')))

# file2 missing sample
missing = [json.loads(l) for l in open(os.path.join(OUT, 'sample_file2_missing.jsonl'), encoding='utf-8') if l.strip()]

c = sqlite3.connect(DB, timeout=30)
c.execute('PRAGMA busy_timeout=30000')

now_done = 0
still_missing = 0
for r in missing:
    tid = str(r.get('task_id'))
    if f"{tid}" in svg or any(b == tid or b.startswith(tid + '_') for b in svg):
        now_done += 1
    else:
        still_missing += 1

out.write('file2 missing sample: total=%d\n' % len(missing))
out.write('now have svg (done): %d\n' % now_done)
out.write('still missing: %d\n' % still_missing)

# geometry
sf = [json.loads(l) for l in open(os.path.join(OUT, 'sample_full.jsonl'), encoding='utf-8') if l.strip()]
geo_missing = 0
for r in sf:
    tid = str(r.get('task_id'))
    if f"{tid}_{r.get('grade')}" in svg or any(b == tid or b.startswith(tid + '_') for b in svg):
        continue
    geo_missing += 1
out.write('geometry missing: %d/362\n' % geo_missing)

c.close()
open('_progress_now.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
