#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify grade 11 vsosh 2020 regional Day 2 fix."""
import ast
import sys
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()

tree = ast.parse(content)
for node in ast.iter_child_nodes(tree):
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == 'OLYMPIADS_DB' for t in node.targets
    ):
        entries = node.value.elts
        print(f"Total entries: {len(entries)}")
        
        # Check vsosh 2020 regional entries for all grades
        for idx in range(len(entries)):
            entry = entries[idx]
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
                            if hasattr(pv, 'value'):
                                pd[pkv] = pv.value
                            elif hasattr(pv, 'n'):
                                pd[pkv] = pv.n
                            elif hasattr(pv, 's'):
                                pd[pkv] = pv.s
                            elif hasattr(pv, 'elts'):
                                pd[pkv] = [x.value if hasattr(x, 'value') else str(x) for x in pv.elts]
                            else:
                                pd[pkv] = str(pv)
                        probs.append(pd)
                    d[key] = probs
                    d['problems'] = probs
            
            slug = d.get('slug', '')
            grade = d.get('grade', '')
            rkey = d.get('round_key', d.get('round', ''))
            year = d.get('year', '')
            
            if slug == 'vsosh' and rkey == 'regional' and year == 2020:
                problems = d.get('problems', [])
                has_day = any('day' in p for p in problems)
                day2_count = sum(1 for p in problems if p.get('day') == 2)
                print(f"\nIndex {idx}: grade={grade}, id={d.get('id','')}")
                print(f"  Problems: {len(problems)}")
                print(f"  Has day field: {has_day}")
                print(f"  Day 1: {sum(1 for p in problems if p.get('day')==1)}")
                print(f"  Day 2: {day2_count}")
                if day2_count > 0:
                    print(f"  Day 2 problems:")
                    for p in problems:
                        if p.get('day') == 2:
                            txt = str(p.get('text', ''))[:100]
                            print(f"    #{p.get('num','?')}: {txt}")
        
        break
