# -*- coding: utf-8 -*-
"""Разбить sample_file2.jsonl на 4 волны."""
import io, sys, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')

rows = [json.loads(l) for l in open(os.path.join(_OUT, 'sample_file2.jsonl'), encoding='utf-8')]
n = len(rows)
waves = 4
per = (n + waves - 1) // waves
for w in range(waves):
    chunk = rows[w * per:(w + 1) * per]
    p = os.path.join(_OUT, f'sample_file2_wave{w+1}.jsonl')
    with open(p, 'w', encoding='utf-8') as f:
        for r in chunk:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f"wave{w+1}: {len(chunk)} tasks -> {os.path.basename(p)}")
