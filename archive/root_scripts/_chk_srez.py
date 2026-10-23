# -*- coding: utf-8 -*-
import io, sys, json, os, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

f = 'FORMYLA_SREZ.jsonl'
rows = [json.loads(l) for l in io.open(f, encoding='utf-8') if l.strip()]
have = sum(1 for r in rows if r.get('figure_json'))
svg = set(os.path.basename(x).replace('.svg', '') for x in glob.glob('scripts/batch/out/svg_ready/*.svg'))
print('srez total:', len(rows))
print('с figure_json:', have)
print('без figure_json:', len(rows) - have)
print('svg_ready:', len(svg))
