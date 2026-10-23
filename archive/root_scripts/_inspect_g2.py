#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json, sys
bank = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))
print(f'Total: {len(bank)}', flush=True)

# Find grade=2 tasks
g2 = [t for t in bank if str(t.get('grade',''))=='2']
print(f'grade=="2": {len(g2)}', flush=True)
for t in g2:
    print(f'  id={t.get("original_id","?")} level={t.get("level")} target={t.get("target_level")} grade={t.get("grade")} (type={type(t.get("grade")).__name__})', flush=True)

# G2|L1
g2l1 = [t for t in bank if t.get('level')==1 and str(t.get('grade',''))=='2']
print(f'\nG2|L1 count: {len(g2l1)}', flush=True)
for t in g2l1:
    print(f'  id={t.get("original_id","?")} idx={t.get("source_index")} topic={t.get("topic","?")}', flush=True)
    print(f'  text={str(t.get("task_text",""))[:200]}', flush=True)

# G6|L1  
g6l1 = [t for t in bank if t.get('level')==1 and str(t.get('grade',''))=='6']
print(f'\nG6|L1 count: {len(g6l1)}', flush=True)
for t in g6l1:
    print(f'  id={t.get("original_id","?")} idx={t.get("source_index")} topic={t.get("topic","?")}', flush=True)
    print(f'  text={str(t.get("task_text",""))[:200]}', flush=True)

# Show sample of grade types
grades = set()
for t in bank:
    g = t.get('grade')
    grades.add((type(g).__name__, str(g)[:10]))
print(f'\nGrade types found: {grades}', flush=True)
