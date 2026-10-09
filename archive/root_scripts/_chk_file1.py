# -*- coding: utf-8 -*-
import io, sys, json, os, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

base = 'scripts/batch/out/'
svg = set(os.path.basename(f).replace('.svg', '') for f in glob.glob(base + 'svg_ready/*.svg'))

print('=== Downloads jsonl task counts ===')
for f in [r'C:\Users\Redmi\Downloads\geometry_needs_figure (1).jsonl',
          r'C:\Users\Redmi\Downloads\geometry_needs_figure (2).jsonl',
          r'C:\Users\Redmi\Downloads\geometry_needs_figure.jsonl']:
    if os.path.exists(f):
        n = sum(1 for l in io.open(f, encoding='utf-8', errors='ignore') if l.strip())
        print(os.path.basename(f), '->', n)

print('\n=== out/*.jsonl task counts + prefixes ===')
for name in ['sample_full.jsonl', 'sample_missing.jsonl', 'sample_100.jsonl',
             'sample_file2.jsonl', 'sample_wave2.jsonl']:
    p = base + name
    if not os.path.exists(p):
        continue
    rows = [json.loads(l) for l in io.open(p, encoding='utf-8') if l.strip()]
    prefixes = {}
    for r in rows:
        t = str(r.get('task_id', ''))
        prefixes[t[:4]] = prefixes.get(t[:4], 0) + 1
    print(name, len(rows), 'tasks, prefixes:', dict(sorted(prefixes.items())))
