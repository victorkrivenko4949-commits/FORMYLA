#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostic: Check current state of idx 1042."""
import ast, json, sys, os
os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()

tree = ast.parse(content)
for node in ast.iter_child_nodes(tree):
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'OLYMPIADS_DB' for t in node.targets):
        entries = ast.literal_eval(node.value)
        entry = entries[1042]
        existing = entry.get('problems', [])
        
        out_lines = []
        out_lines.append(f'Grade 10 var 2 (idx 1042): {len(existing)} problems')
        for p in existing:
            d = p.get('day', 'N/A')
            num = p.get('num', '?')
            txt = (str(p.get('text', '')) or '')[:150]
            out_lines.append(f'  Problem {num} (day={d}): {txt}')
        
        day1 = sum(1 for p in existing if p.get('day') == 1)
        day2 = sum(1 for p in existing if p.get('day') == 2)
        out_lines.append(f'\nDay 1: {day1} problems')
        out_lines.append(f'Day 2: {day2} problems')
        
        output = '\n'.join(out_lines)
        print(output)
        
        with open('_diag_1042_out.txt', 'w', encoding='utf-8') as f:
            f.write(output)
        break
