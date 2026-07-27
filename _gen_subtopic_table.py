#!/usr/bin/env python
"""Generate subtopic table for FINAL_REPORT.md with proper UTF-8 output."""
import json
from collections import defaultdict

bank = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))
source = json.load(open(r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_completed.json', 'r', encoding='utf-8'))
target = [t for t in bank if t.get('target_level', '') in {'L1', 'L2', 'L3'}]

# Group by grade|level|subtopic
cells = defaultdict(list)
gl_cells = defaultdict(list)

for t in target:
    si = t.get('source_index')
    oid = t.get('original_id', '?')
    grade = t.get('class_level')
    level = t.get('target_level', '?')
    
    gl_key = f"G{grade or '?'}|{level}"
    gl_cells[gl_key].append(oid)
    
    subtopic = None
    if si is not None and 0 <= si < len(source):
        src = source[si]
        if grade is None and src.get('grade') is not None:
            grade = src['grade']
        subtopic = src.get('subtopic', '').strip()
    
    if not subtopic:
        subtopic = '__NO_SUBTOPIC__'
    
    cell_key = f"G{grade or '?'}|{level}|{subtopic}"
    cells[cell_key].append(oid)

# Build subtopics per grade|level
by_gl = defaultdict(list)
for k in cells:
    parts = k.split('|', 2)
    gl = f"{parts[0]}|{parts[1]}"
    by_gl[gl].append(parts[2] if len(parts) > 2 else k)

# Print header
print("### 1.4 Распределение по подтемам (subtopic)")
print()
print("Каждая grade|level-ячейка разбивается на подтемы из исходного датасета (`source_index -> subtopic`).")
print(f"Всего найдено **{len(cells)} grade|level|subtopic-ячеек** среди {len(target)} L1-L3 задач (аудированные поля).")
print()
print("| Grade|Level | Кол-во подтем | Список подтем |")
print("|-------------|--------|--------------|")

for gl in sorted(by_gl):
    subs = sorted(set(by_gl[gl]))
    sub_list = ", ".join(subs)
    print(f"| {gl} | {len(subs)} | {sub_list} |")

print()
perfect = sum(1 for v in cells.values() if len(v) == 5)
under = sum(1 for v in cells.values() if 0 < len(v) < 5)
over = sum(1 for v in cells.values() if len(v) > 5)
print(f"**Итого**: {len(cells)} subtopic-ячеек, из которых:")
print(f"- **{perfect}** имеют ровно 5 задач (perfect)")
print(f"- **{under}** имеют 1-4 задачи (underfilled)")
print(f"- **{over}** имеют >5 задач (overfilled)")
print()

# Also print detailed per-subtopic counts for overfilled cells
print("### Детализация переполненных subtopic-ячеек")
print()
print("| Ячейка | Задач |")
print("|--------|-------|")
for k in sorted(cells):
    v = cells[k]
    if len(v) > 5:
        print(f"| {k} | {len(v)} |")
