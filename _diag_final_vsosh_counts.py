#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Final diagnostic: Check vsosh 2020 regional entries have 10 problems (5+5)."""
import ast
import json

with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()
tree = ast.parse(content)
for node in ast.iter_child_nodes(tree):
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == 'OLYMPIADS_DB' for t in node.targets
    ):
        entries = node.value.elts
        break

# Convert AST to dict
def ast_to_dict(ast_node):
    if isinstance(ast_node, ast.Dict):
        result = {}
        for k, v in zip(ast_node.keys, ast_node.values):
            key = ast_to_dict(k)
            result[key] = ast_to_dict(v)
        return result
    elif isinstance(ast_node, ast.List):
        return [ast_to_dict(elem) for elem in ast_node.elts]
    elif isinstance(ast_node, ast.Constant):
        return ast_node.value
    elif isinstance(ast_node, ast.Str):
        return ast_node.s
    elif isinstance(ast_node, ast.Num):
        return ast_node.n
    elif isinstance(ast_node, ast.NameConstant):
        return ast_node.value
    elif isinstance(ast_node, ast.UnaryOp) and isinstance(ast_node.op, ast.USub):
        return -ast_to_dict(ast_node.operand)
    else:
        return None

output_lines = []
output_lines.append("=" * 70)
output_lines.append("VSOSH 2020 REGIONAL - FINAL VERIFICATION")
output_lines.append("=" * 70)

all_ok = True
for entry_ast in entries:
    d = ast_to_dict(entry_ast)
    if d.get('olympiad') == 'vsosh' and d.get('year') == 2020 and d.get('round') == 'regional':
        probs = d.get('problems', [])
        day1 = sum(1 for p in probs if p.get('day') == 1)
        day2 = sum(1 for p in probs if p.get('day') == 2)
        total = len(probs)
        
        status = "OK" if (total == 10 and day1 == 5 and day2 == 5) else "PROBLEM!"
        if status == "PROBLEM!":
            all_ok = False
        
        nums_day = {}
        for p in probs:
            n = p.get('num')
            d2 = p.get('day')
            nums_day[n] = d2
        
        line = f"  id={d.get('id')} grade={d.get('grade')} var={d.get('variant')}: {total} problems (D1={day1} D2={day2}) [{status}]"
        output_lines.append(line)
        
        if status == "PROBLEM!":
            output_lines.append(f"    Nums->Day: {json.dumps(nums_day, ensure_ascii=False)}")

output_lines.append("=" * 70)
if all_ok:
    output_lines.append("ALL ENTITIES HAVE 10 PROBLEMS (5 Day 1 + 5 Day 2)")
else:
    output_lines.append("SOME ENTITIES HAVE INCORRECT PROBLEM COUNTS!")

output_lines.append("=" * 70)

# Write to file
with open('_diag_final_vsosh_counts.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output_lines))

print("Written to _diag_final_vsosh_counts.txt")
print('\n'.join(output_lines))
