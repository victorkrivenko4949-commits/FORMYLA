#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Debug: inspect first few entries in OLYMPIADS_DB to see AST structure."""
import ast

with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()

tree = ast.parse(content)

# Find OLYMPIADS_DB assignment
for node in ast.iter_child_nodes(tree):
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == 'OLYMPIADS_DB':
                if isinstance(node.value, ast.List):
                    entries = node.value.elts
                    print(f"Total entries: {len(entries)}")
                    
                    # Print first 5 entries' dict keys and values
                    for idx in range(min(5, len(entries))):
                        elt = entries[idx]
                        if isinstance(elt, ast.Dict):
                            print(f"\n--- Entry {idx} ---")
                            for k, v in zip(elt.keys, elt.values):
                                ktype = type(k).__name__
                                vtype = type(v).__name__
                                kval = ''
                                vval = ''
                                if isinstance(k, ast.Constant):
                                    kval = repr(k.value)
                                elif isinstance(k, ast.Str):
                                    kval = repr(k.s)
                                else:
                                    kval = ktype
                                
                                if isinstance(v, ast.Constant):
                                    vval = repr(v.value)[:60]
                                elif isinstance(v, ast.Str):
                                    vval = repr(v.s)[:60]
                                elif isinstance(v, ast.List):
                                    vval = f"List(len={len(v.elts)})"
                                elif isinstance(v, ast.Dict):
                                    vval = f"Dict(len={len(v.keys)})"
                                elif isinstance(v, ast.Name):
                                    vval = f"Name(id={v.id})"
                                else:
                                    vval = vtype
                                
                                print(f"  {ktype} key={kval} -> {vtype} val={vval}")
                        else:
                            print(f"\n--- Entry {idx} is {type(elt).__name__} ---")
                    
                    # Now search for vsosh - print any entries with slug='vsosh'
                    print("\n\n=== Searching for 'vsosh' in all entries ===")
                    count = 0
                    for i, elt in enumerate(entries):
                        if isinstance(elt, ast.Dict):
                            slug_val = None
                            year_val = None
                            for k, v in zip(elt.keys, elt.values):
                                if isinstance(k, ast.Constant) and k.value == 'slug':
                                    if isinstance(v, ast.Constant):
                                        slug_val = v.value
                                    elif isinstance(v, ast.Str):
                                        slug_val = v.s
                                elif isinstance(k, ast.Constant) and k.value == 'year':
                                    if isinstance(v, ast.Constant):
                                        year_val = v.value
                                    elif isinstance(v, ast.Str):
                                        year_val = v.s
                            if slug_val == 'vsosh':
                                count += 1
                                round_val = '?'
                                grade_val = '?'
                                prob_count = 0
                                for k, v in zip(elt.keys, elt.values):
                                    if isinstance(k, ast.Constant):
                                        if k.value == 'round_key' and isinstance(v, ast.Constant):
                                            round_val = v.value
                                        elif k.value == 'grade' and isinstance(v, ast.Constant):
                                            grade_val = v.value
                                        elif k.value == 'problems' and isinstance(v, ast.List):
                                            prob_count = len(v.elts)
                                print(f"  [{i}] round={round_val}, grade={grade_val}, year={year_val}, problems={prob_count}")
                    print(f"Total vsosh entries: {count}")
                    
                    # Also search by text "vsosh" in case slug is different
                    print("\n=== Searching entries with 'vsosh' anywhere ===")
                    for i, elt in enumerate(entries[:100]):
                        if isinstance(elt, ast.Dict):
                            for k, v in zip(elt.keys, elt.values):
                                if isinstance(k, ast.Constant):
                                    if isinstance(v, ast.Constant) and isinstance(v.value, str) and 'vsosh' in v.value.lower():
                                        print(f"  [{i}] key={k.value} contains 'vsosh': val={v.value[:80]}")
                    break
    if isinstance(node, ast.Assign):
        break
