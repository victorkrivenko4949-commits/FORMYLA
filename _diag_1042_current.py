#!/usr/bin/env python3
"""Diagnose current state of idx 1042 in olympiads.py - output with proper encoding"""
import ast, json, os

out_path = '_diag_1042_current.txt'
with open(out_path, 'w', encoding='utf-8') as out:
    out.write("=== Current state of idx 1042 ===\n\n")

    with open('olympiads.py', 'r', encoding='utf-8') as f:
        content = f.read()

    tree = ast.parse(content)
    found = False
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == 'OLYMPIADS_DB' for t in node.targets
        ):
            entries = node.value.elts
            for i, entry in enumerate(entries):
                d = {}
                for k, v in zip(entry.keys, entry.values):
                    key = k.value if isinstance(k, ast.Constant) else k.s
                    if isinstance(v, ast.Constant):
                        d[key] = v.value
                    elif isinstance(v, ast.List):
                        val_list = []
                        for elem in v.elts:
                            if isinstance(elem, ast.Dict):
                                ed = {}
                                for ek, ev in zip(elem.keys, elem.values):
                                    ek_val = ek.value if isinstance(ek, ast.Constant) else ek.s
                                    if isinstance(ev, ast.Constant):
                                        ed[ek_val] = ev.value
                                    elif isinstance(ev, ast.List):
                                        ed[ek_val] = [ev2.value for ev2 in ev.elts if isinstance(ev2, ast.Constant)]
                                    else:
                                        ed[ek_val] = str(ev)[:80]
                                val_list.append(ed)
                            elif isinstance(elem, ast.Constant):
                                val_list.append(elem.value)
                        d[key] = val_list
                    else:
                        d[key] = str(v)[:80]

                if d.get('id') == 517:
                    found = True
                    out.write(f'Index {i}: id={d.get("id")}\n')
                    out.write(f'olympiad={d.get("olympiad")}, grade={d.get("grade")}, year={d.get("year")}\n')
                    problems = d.get('problems', [])
                    out.write(f'Total problems: {len(problems)}\n')
                    for p in problems:
                        num = p.get('num', '?')
                        day = p.get('day', 'N/A')
                        txt = str(p.get('text', ''))[:120].replace('\n', ' ')
                        ans = str(p.get('answer', ''))[:60].replace('\n', ' ')
                        out.write(f'  Problem {num} (day={day}): {txt}\n')
                        out.write(f'    Answer: {ans}\n')

    if not found:
        # Search by other criteria
        out.write("\n--- Searching by olympiad/grade/year ---\n")
        for i, entry in enumerate(entries):
            d = {}
            for k, v in zip(entry.keys, entry.values):
                key = k.value if isinstance(k, ast.Constant) else k.s
                if isinstance(v, ast.Constant):
                    d[key] = v.value
                elif isinstance(v, ast.List):
                    d[key] = f"[LIST with {len(v.elts)} elems]"
                else:
                    d[key] = str(v)[:30]
            
            if (d.get('olympiad') == 'vsosh' and d.get('grade') == 10 and 
                d.get('year') == 2020 and d.get('round') == 'regional'):
                out.write(f'Index {i}: id={d.get("id")}, problems={d.get("problems")}\n')

print(f"Done. Output written to {out_path}")
