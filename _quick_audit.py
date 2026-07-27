#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick audit of existing tasks and taxonomy"""
import json, os
from collections import Counter

print("="*60)
print("АНАЛИЗ СУЩЕСТВУЮЩИХ ЗАДАЧ И ТАКСОНОМИИ")
print("="*60)

# 1. Victor2 generated bank
if os.path.exists('victor2_generated.json'):
    with open('victor2_generated.json','rb') as f:
        data = json.loads(f.read())
    print(f"\n1. victor2_generated.json: {len(data)} записей")
    
    cells = Counter()
    by_level = Counter()
    by_grade = Counter()
    no_stmt = 0
    for d in data:
        stmt = d.get('statement','') or ''
        if not stmt.strip():
            no_stmt += 1
            continue
        lv = d.get('level',0)
        if isinstance(lv,str) and lv.startswith('L'):
            lv = int(lv[1])
        lv = int(lv or 0)
        grade = d.get('grade',0)
        tid = d.get('theme_id','')
        if 1 <= lv <= 3 and grade in (5,6,7,8,9,10,11):
            cells[f'G{grade}|{tid}|L{lv}'] += 1
            by_level[lv] += 1
            by_grade[grade] += 1
    
    print(f"   С условием: {len(data)-no_stmt}")
    print(f"   Всего ячеек L1-L3: {len(cells)}")
    for l in [1,2,3]:
        print(f"     L{l}: {by_level[l]} задач, {sum(1 for k in cells if f'L{l}' in k)} ячеек")
    print(f"   По классам:")
    for g in sorted(by_grade):
        print(f"     {g} кл: {by_grade[g]} задач")

# 2. Taxonomy
print(f"\n2. taxonomy_by_grade.json:")
with open('taxonomy_by_grade.json','rb') as f:
    tax = json.loads(f.read())

gt = tax.get('grade_theme_map',{})
print(f"   Классы: {sorted(gt.keys())}")
total_sub = 0
for g in sorted(gt):
    themes = gt[g]['themes']
    subtopics = 0
    for tid in themes:
        td = tax.get('theme_definitions',{}).get(tid,{})
        subtopics += len(td.get('subtopics',[]))
    total_sub += subtopics
    print(f"   {g} класс: {len(themes)} тем, {subtopics} подтем, темы={themes}")

print(f"\n   ВСЕГО подтем: {total_sub}")
print(f"   ЦЕЛЬ ячеек (подтемы x3 уровня): {total_sub * 3}")
print(f"   ЦЕЛЬ задач (x5): {total_sub * 3 * 5}")

# 3. Other files
for fn in ['curated_bank_L1_L5_fixed.json','formyla_dataset_slightly_fixed.json','tasks_9_11.json','diagnostic_tasks.json']:
    if os.path.exists(fn):
        try:
            with open(fn,'rb') as f:
                d2 = json.loads(f.read())
            if isinstance(d2,list):
                print(f"\n3. {fn}: {len(d2)} записей")
            elif isinstance(d2,dict):
                print(f"\n3. {fn}: dict keys={list(d2.keys())[:3]}")
        except:
            print(f"\n3. {fn}: ошибка")

# 4. Check if pipeline produced anything
outdir = 'l1_l3_generation/max_fill_20260722_111737'
print(f"\n4. Директория вывода:")
if os.path.isdir(outdir):
    files = os.listdir(outdir)
    print(f"   Файлов: {files}")
    for fn in files:
        fp = os.path.join(outdir, fn)
        print(f"   {fn}: {os.path.getsize(fp)} bytes")
else:
    print(f"   {outdir} - НЕ СУЩЕСТВУЕТ (пайплайн не создал ни одного файла)")
