#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find vsosh 2020 regional entries in olympiads.py and extract their data."""
import sys, json, ast

with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()

tree = ast.parse(content)

# Find OLYMPIADS_DB assignment
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == 'OLYMPIADS_DB':
                if isinstance(node.value, ast.List):
                    entries = node.value.elts
                    print(f"Total OLYMPIADS_DB entries: {len(entries)}", flush=True)
                    
                    # Find vsosh 2020 entries
                    results = []
                    for i, elt in enumerate(entries):
                        if not isinstance(elt, ast.Dict):
                            continue
                        d = {}
                        for k, v in zip(elt.keys, elt.values):
                            if isinstance(k, ast.Constant):
                                d[k.value] = v
                        
                        if 'slug' not in d or not isinstance(d['slug'], ast.Constant) or d['slug'].value != 'vsosh':
                            continue
                        if 'year' not in d or not isinstance(d['year'], ast.Constant) or d['year'].value != 2020:
                            continue
                        
                        slug = d['slug'].value
                        year = d['year'].value
                        round_key = d.get('round_key', ast.Constant(value='?'))
                        round_key = round_key.value if isinstance(round_key, ast.Constant) else '?'
                        grade = d.get('grade', ast.Constant(value='?'))
                        grade = grade.value if isinstance(grade, ast.Constant) else '?'
                        problems = d.get('problems', ast.List(elts=[]))
                        problems_list = problems.elts if isinstance(problems, ast.List) else []
                        
                        print(f"Index {i}: slug={slug}, year={year}, round={round_key}, grade={grade}, problems={len(problems_list)}", flush=True)
                        
                        # Extract problem data as JSON
                        prob_data = []
                        for p in problems_list:
                            if isinstance(p, ast.Dict):
                                pdata = {}
                                for pk, pv in zip(p.keys, p.values):
                                    if isinstance(pk, ast.Constant):
                                        key = pk.value
                                        if isinstance(pv, ast.Constant):
                                            pdata[key] = pv.value
                                        elif isinstance(pv, ast.List):
                                            pdata[key] = [e.value for e in pv.elts if isinstance(e, ast.Constant)]
                                        else:
                                            pdata[key] = str(type(pv).__name__)
                                prob_data.append(pdata)
                        
                        results.append({
                            'index': i,
                            'round_key': round_key,
                            'grade': grade,
                            'problems': prob_data
                        })
                    
                    # Output results as JSON for safe reading
                    out = {'total_entries': len(entries), 'vsosh_2020': results}
                    with open('_vsosh_data.json', 'w', encoding='utf-8') as fout:
                        json.dump(out, fout, ensure_ascii=False, indent=2)
                    print(f"\nSaved to _vsosh_data.json", flush=True)
                    
                    # Print summary
                    print(f"\nFound {len(results)} vsosh 2020 entries:", flush=True)
                    for r in results:
                        print(f"  Index {r['index']}: round={r['round_key']}, grade={r['grade']}, problems={len(r['problems'])}", flush=True)
                        for p in r['problems']:
                            text_preview = (p.get('text','') or '')[:60]
                            answer_preview = (p.get('answer','') or '')[:40]
                            sol_len = len(p.get('solution','') or '')
                            print(f"    Problem {p.get('num','?')}: {text_preview}... | answer={answer_preview}... | solution_len={sol_len}", flush=True)
                    
                    sys.exit(0)
    
    # Only check first level of assignments
    if isinstance(node, ast.Module):
        continue

print("Could not find OLYMPIADS_DB", flush=True)
sys.exit(1)
