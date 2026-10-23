#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find vsosh 2020 regional entries in olympiads.py and show their problems."""

import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

# Execute olympiads.py to get OLYMPIADS_DB
exec(compile(open('olympiads.py', encoding='utf-8').read(), 'olympiads.py', 'exec'))

# Find vsosh 2020 entries
for i, entry in enumerate(OLYMPIADS_DB):
    if entry.get('slug') == 'vsosh' and entry.get('year') == 2020:
        problems = entry.get('problems', [])
        print(f'\nIndex {i}: round="{entry.get("round_key")}", grade={entry.get("grade")}, problems={len(problems)}')
        for p in problems:
            print(f'  Problem {p.get("num")}: keys={list(p.keys())}, text_preview={p.get("text","")[:80]}...')
            print(f'    answer={p.get("answer","")[:60]}')
            sol = p.get('solution', '')
            if sol:
                print(f'    solution_len={len(sol)}')
            else:
                print(f'    solution=None')
