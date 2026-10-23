# -*- coding: utf-8 -*-
import glob, io, sys, sqlite3, collections, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()
out.write("SVG total: %d\n" % len(glob.glob('scripts/batch/out/svg_ready/*.svg')))
c = sqlite3.connect(r'instance/formyla.db')
out.write("db jobs (1301): %s\n" % dict(collections.Counter(r[0] for r in c.execute('SELECT status FROM figure_build_jobs WHERE user_id=1301').fetchall())))
if os.path.exists('scripts/batch/out/results.jsonl'):
    out.write("results lines: %d\n" % sum(1 for _ in open('scripts/batch/out/results.jsonl', encoding='utf-8')))
if os.path.exists('scripts/batch/out/failed.jsonl'):
    out.write("failed lines: %d\n" % sum(1 for _ in open('scripts/batch/out/failed.jsonl', encoding='utf-8')))
open('_status2.txt', 'w', encoding='utf-8').write(out.getvalue())
print('done')
