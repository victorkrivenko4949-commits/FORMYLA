#!/usr/bin/env python3
"""Quick check of current state"""
import json, re

with open('all_methods_real_final.json', 'r', encoding='utf-8') as f:
    methods = json.load(f)

print("=== Problem 1 (E8,E12,E14,E15,F3) ===")
for code in ['E8','E12','E14','E15','F3']:
    for m in methods:
        if m['method_code']==code:
            we=m.get('worked_example_md','')
            tasks=we.split('### Задача')
            n=len(tasks)-1
            all_ok=all('**Ответ:**' in t and '**Что было главным:**' in t for t in tasks[1:])
            print(f"  {code}: {n} tasks, all_ok={all_ok}")

print("\n=== Problem 2 (training first task) ===")
for code in ['G1','G2','G3','G4','G5','G7','H3','H5','E5a','F14','F15','F16','F17','H4']:
    for m in methods:
        if m['method_code']==code:
            we=m.get('worked_example_md','')
            parts=we.split('### Задача')
            n=len(parts)-1
            src=""
            if len(parts)>1:
                sm=re.search(r'\*\*Источник:\*\*\s*(.+?)(?:\n|$)', parts[1])
                src=sm.group(1)[:80] if sm else "NONE"
            training='тренировочная' in src.lower() or 'классическая задача' in src.lower() or n==0
            print(f"  {code}: {n} tasks, src={src}, training={training}")
