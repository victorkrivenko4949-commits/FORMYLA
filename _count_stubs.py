#!/usr/bin/env python3
"""Count stub tasks in olympiads.py"""
import ast

raw = open('olympiads.py', 'r', encoding='utf-8').read()
DB = ast.literal_eval(raw.split('=', 1)[1].strip())

stub_markers = [
    'требует рисун', 'не удалось найти', 'официальный источник',
    'не удалось восстановить', 'см. официальн', 'нужен чертёж', 'нужен рисунок',
]

total = 0
stubs = 0
stub_examples = []

for rec in DB:
    for p in rec.get('problems', []):
        total += 1
        sol = p.get('solution', '')
        s = str(sol).strip()
        if not s:
            stubs += 1
            if len(stub_examples) < 5:
                stub_examples.append((rec.get('olympiad','?'), p.get('num','?'), 'empty', None))
            continue
        sl = s.lower()
        is_stub = False
        reason = ''
        for m in stub_markers:
            if m in sl:
                is_stub = True
                reason = f'marker:{m}'
                break
        if not is_stub and len(s) < 40:
            is_stub = True
            reason = f'short({len(s)})'
        if is_stub:
            stubs += 1
            if len(stub_examples) < 5:
                stub_examples.append((rec.get('olympiad','?'), p.get('num','?'), reason, sl[:80]))

print(f'Records: {len(DB)}')
print(f'Total problems: {total}')
print(f'Stub problems: {stubs}')
print(f'Non-stub: {total - stubs}')
print()
print('Examples:')
for o, n, r, prev in stub_examples:
    print(f'  {o} #{n} [{r}]')
    if prev:
        print(f'    -> {prev}')
