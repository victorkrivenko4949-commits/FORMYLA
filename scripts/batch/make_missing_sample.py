# -*- coding: utf-8 -*-
"""Создать sample из недостающих задач (те, что ещё не имеют SVG)."""
import io, sys, os, glob, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
sample_full = [json.loads(l) for l in open(os.path.join(_OUT, 'sample_full.jsonl'), encoding='utf-8')]

done_svg = set()
for f in glob.glob(os.path.join(_OUT, 'svg_ready', '*.svg')):
    base = os.path.basename(f).replace('.svg', '')
    done_svg.add(base.rsplit('_', 1)[0])

missing = [r for r in sample_full if r['task_id'] not in done_svg]
out_path = os.path.join(_OUT, 'sample_missing.jsonl')
with open(out_path, 'w', encoding='utf-8') as f:
    for r in missing:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f"missing: {len(missing)} -> {out_path}")
