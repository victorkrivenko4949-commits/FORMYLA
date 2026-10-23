#!/usr/bin/env python
"""Count grade|level|subtopic cells in curated bank by mapping via source_index."""
import json
from collections import defaultdict

bank = json.load(open('curated_bank_L1_L5_fixed.json','r',encoding='utf-8'))
source = json.load(open(r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_completed.json','r',encoding='utf-8'))

print(f"Bank: {len(bank)} tasks, Source: {len(source)} tasks")

target = [t for t in bank if t.get('target_level','') in {'L1','L2','L3'}]
print(f"L1-L3 target tasks: {len(target)}")

cells = defaultdict(list)
gl_cells = defaultdict(list)
mapped = 0
unmapped = 0

for t in target:
    si = t.get('source_index')
    oid = t.get('original_id','?')
    grade = t.get('class_level')
    level = t.get('target_level','?')
    
    gl_key = f"G{grade or '?'}|{level}"
    gl_cells[gl_key].append(oid)
    
    subtopic = None
    if si is not None and 0 <= si < len(source):
        src = source[si]
        if grade is None and src.get('grade') is not None:
            grade = src['grade']
        subtopic = src.get('subtopic','').strip()
        mapped += 1
    else:
        unmapped += 1
    
    if not subtopic:
        subtopic = '__NO_SUBTOPIC__'
    
    cell_key = f"G{grade or '?'}|{level}|{subtopic}"
    cells[cell_key].append(oid)

print(f"Mapped: {mapped}, Unmapped: {unmapped}")
print(f"\n=== Grade|Level cells: {len(gl_cells)} ===")
for k in sorted(gl_cells):
    print(f"  {k}: {len(gl_cells[k])} tasks")

print(f"\n=== Grade|Level|Subtopic cells: {len(cells)} ===")
for k in sorted(cells):
    print(f"  {k}: {len(cells[k])} tasks")

by_gl = defaultdict(list)
for k in cells:
    parts = k.split('|', 2)
    gl = f"{parts[0]}|{parts[1]}"
    by_gl[gl].append(parts[2] if len(parts) > 2 else k)

print(f"\n=== Subtopics per grade|level ===")
for gl in sorted(by_gl):
    subs = sorted(by_gl[gl])
    print(f"  {gl}: {len(subs)} subtopics -> {subs}")

print(f"\n=== Summary ===")
perfect = sum(1 for v in cells.values() if len(v) == 5)
under = sum(1 for v in cells.values() if 0 < len(v) < 5)
over = sum(1 for v in cells.values() if len(v) > 5)
print(f"Total subtopic cells: {len(cells)}")
print(f"  Perfect (5 tasks): {perfect}")
print(f"  Underfilled (1-4): {under}")
print(f"  Overfilled (>5): {over}")
