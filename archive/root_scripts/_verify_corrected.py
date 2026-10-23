#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Corrected verification — uses 'olympiad' field (not 'slug')."""
import ast, json

with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()

tree = ast.parse(content)
results = []

for node in ast.iter_child_nodes(tree):
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == 'OLYMPIADS_DB' for t in node.targets
    ):
        entries = node.value.elts
        results.append({"msg": f"Total entries: {len(entries)}"})

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

            # CORRECTED: use 'olympiad' field (not 'slug')
            slug = d.get('olympiad', '')
            if slug == 'vsosh':
                grade = d.get('grade', '?')
                year = d.get('year', '?')
                # round_key doesn't exist — the field is just 'round'
                rkey = d.get('round', '?')
                problems = d.get('problems', [])
                day1 = sum(1 for p in problems if p.get('day') == 1)
                day2 = sum(1 for p in problems if p.get('day') == 2)
                total = len(problems)
                status = 'OK' if total >= 10 and day2 >= 5 else 'MISSING'
                results.append({
                    "idx": idx, "grade": grade, "year": year,
                    "round": rkey, "problems": total,
                    "day1": day1, "day2": day2, "status": status
                })

        break

with open('_verify_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("Done", flush=True)
