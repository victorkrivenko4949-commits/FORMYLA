# -*- coding: utf-8 -*-
import io, sys, os, glob, json, sqlite3, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

svg = glob.glob('scripts/batch/out/svg_ready/*.svg')
out.write(f"svg_ready files: {len(svg)}\n")

c = sqlite3.connect(r'instance/formyla.db')
out.write(f"db jobs (user 1301): {dict(collections.Counter(r[0] for r in c.execute('SELECT status FROM figure_build_jobs WHERE user_id=1301').fetchall()))}\n")

sample = set()
for l in open('scripts/batch/out/sample_full.jsonl', encoding='utf-8'):
    sample.add(json.loads(l)['task_id'])

done_svg = set()
for f in svg:
    base = os.path.basename(f).replace('.svg', '')
    parts = base.rsplit('_', 1)
    done_svg.add(parts[0])

out.write(f"sample total: {len(sample)}, done svg: {len(done_svg)}\n")
missing = sample - done_svg
out.write(f"missing (no svg): {len(missing)}\n")
for m in sorted(missing)[:30]:
    out.write(f"  {m}\n")

open('_status.txt', 'w', encoding='utf-8').write(out.getvalue())
print('done')
