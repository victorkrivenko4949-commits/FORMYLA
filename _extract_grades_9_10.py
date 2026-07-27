#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract existing Day 1 problems for grades 9 and 10 (vsosh 2020 regional)."""
import ast
import json
import sys
import os

# Redirect stdout to file to avoid terminal encoding issues
sys.stdout = open('_extract_output.txt', 'w', encoding='utf-8')

with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()

tree = ast.parse(content)

for node in ast.iter_child_nodes(tree):
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == 'OLYMPIADS_DB' for t in node.targets
    ):
        entries = node.value.elts
        print(f"Total entries: {len(entries)}", flush=True)
        
        target_indices = [1037, 1041, 1042]
        
        for idx in target_indices:
            if idx >= len(entries):
                print(f"\nIndex {idx} out of range!", flush=True)
                continue
            
            entry_ast = entries[idx]
            
            # Try to extract as dict
            try:
                d = ast.literal_eval(entry_ast)
            except:
                d = {}
            
            print(f"\n{'='*70}", flush=True)
            print(f"INDEX {idx}: grade={d.get('grade','?')}, year={d.get('year','?')}", flush=True)
            print(f"  olympiad: {d.get('olympiad','?')}", flush=True)
            print(f"  round: {d.get('round','?')}", flush=True)
            print(f"  round_title: {d.get('round_title','?')}", flush=True)
            print(f"  id: {d.get('id','?')}", flush=True)
            
            problems = d.get('problems', [])
            print(f"  Total problems: {len(problems)}", flush=True)
            
            for p in problems:
                num = p.get('num', '?')
                text_preview = (p.get('text', '') or '')[:200]
                has_day = 'day' in p
                day_val = p.get('day', '-')
                answer = (p.get('answer', '') or '')[:100]
                solution = (p.get('solution', '') or '')[:100]
                print(f"    Problem {num}: day={day_val}, has_day={has_day}", flush=True)
                print(f"      Text: {text_preview}", flush=True)
                print(f"      Answer: {answer}", flush=True)
                print(f"      Solution: {solution}", flush=True)
            
            # Save full entry to JSON for inspection
            with open(f'_entry_{idx}.json', 'w', encoding='utf-8') as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            print(f"  Saved to _entry_{idx}.json", flush=True)
        
        break

sys.stdout.close()
print("Done! Output saved to _extract_output.txt", flush=True)
