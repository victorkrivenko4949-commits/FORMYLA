# -*- coding: utf-8 -*-
"""Сколько file2-задач уже имеют SVG и сколько реально недостаёт."""
import io, sys, os, json, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

OUT = 'scripts/batch/out'
SVG = os.path.join(OUT, 'svg_ready')

# все f2_*.svg -> base (f2_<idx>)
svg_files = glob.glob(os.path.join(SVG, 'f2_*.svg'))
have = set()
for f in svg_files:
    b = os.path.basename(f)[:-4]        # f2_<idx>_<grade>
    have.add(b.rsplit('_', 1)[0])       # f2_<idx>

sample = [json.loads(l) for l in open(os.path.join(OUT, 'sample_file2.jsonl'), encoding='utf-8') if l.strip()]
total = len(sample)
missing = [r for r in sample if r.get('task_id') not in have]

out.write('file2 total=%d\n' % total)
out.write('already have svg=%d\n' % len([r for r in sample if r.get('task_id') in have]))
out.write('missing=%d\n' % len(missing))

# записать sample недостающих
with open(os.path.join(OUT, 'sample_file2_missing.jsonl'), 'w', encoding='utf-8') as f:
    for r in missing:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

out.write('written sample_file2_missing.jsonl (%d)\n' % len(missing))
open('_file2_missing_count.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
