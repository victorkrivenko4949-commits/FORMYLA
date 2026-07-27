#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Simple verification of vsosh 2020 regional day2 fix."""
import ast
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()

tree = ast.parse(content)
for node in ast.iter_child_nodes(tree):
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == 'OLYMPIADS_DB' for t in node.targets
    ):
        entries = node.value.elts
        print(f"Total entries: {len(entries)}", flush=True)
        
        for idx, entry in enumerate(entries):
            d = {}
            for k, v in zip(entry.keys, entry.values):
                key = k.value if hasattr(k, 'value') else str(k)
                if hasattr(v, 'value'):
                    d[key] = v.value
                elif hasattr(v, 'elts'):
                    probs = []
                    for p in v.elts:
                        pd = {}
                        for pk, pv in zip(p.keys, p.values):
                            pkv = pk.value if hasattr(pk, 'value') else str(pk)
                            if hasattr(pv, 'value'): pd[pkv] = pv.value
                            elif hasattr(pv, 'n'): pd[pkv] = pv.n
                            elif hasattr(pv, 's'): pd[pkv] = pv.s
                            elif hasattr(pv, 'elts'): pd[pkv] = [x.value if hasattr(x, 'value') else str(x) for x in pv.elts]
                            else: pd[pkv] = str(pv)
                        probs.append(pd)
                    d[key] = probs
            
            slug = d.get('slug', '')
            rkey = d.get('round_key', d.get('round', ''))
            year = d.get('year', '')
            if slug == 'vsosh' and rkey == 'regional' and year == 2020:
                problems = d.get('problems', [])
                day1 = sum(1 for p in problems if p.get('day') == 1)
                day2 = sum(1 for p in problems if p.get('day') == 2)
                total = len(problems)
                ok = 'OK' if total >= 10 and day2 >= 5 else 'MISSING'
                # Use only ASCII to avoid encoding issues
                print(f"Index {idx}: grade={d.get('grade','?')} id={d.get('id','?')} problems={total} day1={day1} day2={day2} [{ok}]", flush=True)

        break
