#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find vsosh 2020 regional entries by parsing olympiads.py as a module."""
import sys, json, re

# Read the file and try to extract OLYMPIADS_DB
with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find OLYMPIADS_DB = [...] block
start = content.find('OLYMPIADS_DB = [')
if start == -1:
    print("Cannot find OLYMPIADS_DB")
    sys.exit(1)

# Parse using ast
import ast
tree = ast.parse(content)

# Find the OLYMPIADS_DB assignment
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == 'OLYMPIADS_DB':
                if isinstance(node.value, ast.List):
                    entries = node.value.elts
                    print(f"Total OLYMPIADS_DB entries: {len(entries)}")
                    
                    # Find vsosh 2020 entries
                    for i, elt in enumerate(entries):
                        if isinstance(elt, ast.Dict):
                            d = {}
                            for k, v in zip(elt.keys, elt.values):
                                if isinstance(k, ast.Constant):
                                    d[k.value] = v
                            
                            slug = None
                            year = None
                            round_key = None
                            grade = None
                            problems = []
                            
                            if 'slug' in d and isinstance(d['slug'], ast.Constant):
                                slug = d['slug'].value
                            if 'year' in d and isinstance(d['year'], ast.Constant):
                                year = d['year'].value
                            if 'round_key' in d and isinstance(d['round_key'], ast.Constant):
                                round_key = d['round_key'].value
                            if 'grade' in d and isinstance(d['grade'], ast.Constant):
                                grade = d['grade'].value
                            if 'problems' in d and isinstance(d['problems'], ast.List):
                                problems = d['problems'].elts
                            
                            if slug == 'vsosh' and year == 2020:
                                print(f"\nIndex {i}: round={round_key}, grade={grade}, problems={len(problems)}")
                                for p in problems:
                                    if isinstance(p, ast.Dict):
                                        pnum = None
                                        ptext = None
                                        panswer = None
                                        psol = None
                                        for pk, pv in zip(p.keys, p.values):
                                            if isinstance(pk, ast.Constant):
                                                if pk.value == 'num' and isinstance(pv, ast.Constant):
                                                    pnum = pv.value
                                                elif pk.value == 'text' and isinstance(pv, ast.Constant):
                                                    ptext = pv.value[:80]
                                                elif pk.value == 'answer' and isinstance(pv, ast.Constant):
                                                    panswer = pv.value[:60]
                                                elif pk.value == 'solution' and isinstance(pv, ast.Constant):
                                                    psol = f"len={len(pv.value)}"
                                                elif pk.value == 'solution_status' and isinstance(pv, ast.Constant):
                                                    pass  # skip
                                        print(f"  Problem {pnum}: {ptext}")
                                        print(f"    answer={panswer}, solution={psol}")
                break
    break
