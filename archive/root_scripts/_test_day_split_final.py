#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test day splitting for all vsosh 2020 regional entries."""
import ast
import sys
sys.path.insert(0, '.')
from utils.olympiad_days import split_problems_by_day

with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()
tree = ast.parse(content)
for node in ast.iter_child_nodes(tree):
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'OLYMPIADS_DB' for t in node.targets):
        entries = node.value.elts
        break

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

lines = []
lines.append("=" * 70)
lines.append("DAY SPLITTING TEST for vsosh 2020 regional")
lines.append("=" * 70)

all_ok = True
for idx, entry_ast in enumerate(entries):
    d = ast_to_dict(entry_ast)
    if d.get('olympiad') == 'vsosh' and d.get('year') == 2020 and d.get('round') == 'regional':
        probs = d.get('problems', [])
        slug = d.get('olympiad', 'vsosh')
        round_key = d.get('round', 'regional')
        grade = d.get('grade', 10)
        
        lines.append(f"\nidx={idx} id={d.get('id')} grade={grade} var={d.get('variant')}")
        lines.append(f"  Raw problems: {len(probs)}")
        for p in probs:
            lines.append(f"    num={p.get('num')} day={p.get('day')}: {str(p.get('text',''))[:60]}")
        
        try:
            result = split_problems_by_day(probs, slug, round_key, grade)
            lines.append(f"  split_problems_by_day result type: {type(result).__name__}")
            
            if isinstance(result, dict):
                day_keys = sorted(result.keys())
                lines.append(f"  Days: {day_keys}")
                for day in day_keys:
                    probs_day = result[day]
                    lines.append(f"    Day {day}: {len(probs_day)} problems")
                    for p in probs_day:
                        lines.append(f"      num={p.get('num')}")
            elif isinstance(result, list):
                lines.append(f"  List with {len(result)} elements")
                for i, item in enumerate(result):
                    if isinstance(item, list):
                        lines.append(f"    [{i}]: {len(item)} problems")
                        for p in item:
                            lines.append(f"      num={p.get('num')}")
                    else:
                        lines.append(f"    [{i}]: {type(item).__name__}")
            else:
                lines.append(f"  Unexpected type!")
                all_ok = False
                
        except Exception as e:
            lines.append(f"  ERROR: {e}")
            all_ok = False

lines.append("\n" + "=" * 70)
if all_ok:
    lines.append("ALL DAY SPLITTING TESTS PASSED!")
else:
    lines.append("SOME TESTS FAILED!")
lines.append("=" * 70)

with open('_test_day_split_result.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print("Written to _test_day_split_result.txt")
for line in lines:
    print(line)
