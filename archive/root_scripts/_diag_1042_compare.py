#!/usr/bin/env python3
"""Compare problems 6,7 vs 9,10 for entry 1042."""
import ast

with open('olympiads.py', 'r', encoding='utf-8') as f:
    data = f.read()
tree = ast.parse(data)
db = ast.literal_eval(tree.body[0].value)
entry = db[1042]
probs = entry['problems']

lines = []
lines.append(f'Entry idx 1042: grade={entry.get("grade")}, problems count={len(probs)}')
for p in probs:
    lines.append(f'  Problem {p["num"]} (day={p.get("day")}): text[:60]={p["text"][:60]}')

lines.append('')
lines.append('=== Problem 6 text ===')
lines.append(probs[5]['text'])
lines.append('')
lines.append('=== Problem 9 text ===')
lines.append(probs[8]['text'])
lines.append('')
lines.append(f'P6 == P9? {probs[5]["text"] == probs[8]["text"]}')
lines.append('')
lines.append('=== Problem 7 text (first 200 chars) ===')
lines.append(probs[6]['text'][:200])
lines.append('')
lines.append('=== Problem 10 text (first 200 chars) ===')
lines.append(probs[9]['text'][:200])
lines.append('')
lines.append(f'P7 == P10? {probs[6]["text"] == probs[9]["text"]}')

with open('_diag_1042_compare.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print('Done: _diag_1042_compare.txt written')
