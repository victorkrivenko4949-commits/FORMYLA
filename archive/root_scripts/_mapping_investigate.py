#!/usr/bin/env python
import json

BANK_PATH = 'curated_bank_L1_L5_fixed.json'
SOURCE_PATH = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_completed.json'

with open(BANK_PATH, 'r', encoding='utf-8') as f:
    bank = json.load(f)
with open(SOURCE_PATH, 'r', encoding='utf-8') as f:
    source = json.load(f)

lines = []
lines.append(f'Bank: {len(bank)} tasks, Source: {len(source)} tasks')
lines.append(f'Source[0] keys: {list(source[0].keys())}')

# Check if source_index maps directly to array index
match_count = 0
mismatch_count = 0
for t in bank:
    si = t.get('source_index')
    if si is not None and si < len(source):
        s = source[si]
        bg = t.get('grade')
        bl = t.get('level')
        sg = s.get('grade')
        sl = s.get('level')
        if bg == sg and bl == sl:
            match_count += 1
        else:
            mismatch_count += 1
            if mismatch_count <= 3:
                lines.append(f'  MISMATCH: Bank G{bg}|L{bl} (si={si}) -> Source G{sg}|L{sl} id={s.get("id")}')

lines.append(f'\nGrade+Level match via source_index: {match_count}/{len(bank)}')
lines.append(f'Grade+Level mismatch: {mismatch_count}/{len(bank)}')

# Check if source_index maps correctly - sample first 5
lines.append('\nFirst 5 bank tasks mapped via source_index:')
for t in bank[:5]:
    si = t.get('source_index')
    s = source[si]
    lines.append(f'  Bank[{t.get("original_id")}] si={si} G{t.get("grade")}|L{t.get("level")} -> Source id={s.get("id")} G{s.get("grade")}|L{s.get("level")} subtopic={str(s.get("subtopic",""))[:40]}')

# Now count grade|level|subtopic cells by mapping ALL bank tasks to source via source_index
TARGET_GRADES = {2, 5, 6, 7, 8, 9, 10, 11}
TARGET_LEVELS = {1, 2, 3}

from collections import defaultdict
gl_cells = defaultdict(int)
glt_cells = defaultdict(int)
glt_by_task = {}

for t in bank:
    g = t.get('grade')
    l = t.get('level')
    if g in TARGET_GRADES and l in TARGET_LEVELS:
        gl_cells[(g, l)] += 1
        
        si = t.get('source_index')
        subtopic = '__MAPPED_FAILED__'
        if si is not None and si < len(source):
            s = source[si]
            # Verify grade/level match
            if s.get('grade') == g and s.get('level') == l:
                subtopic = s.get('subtopic', '__NO_SUBTOPIC__')
            else:
                subtopic = '__GL_MISMATCH__'
        
        glt_cells[(g, l, subtopic)] += 1
        glt_by_task[t.get('original_id', '?')] = (g, l, subtopic)

lines.append(f'\n=== Grade|Level cells (L1-L3 target): {len(gl_cells)} ===')
for k in sorted(gl_cells.keys()):
    lines.append(f'  G{k[0]}|L{k[1]}: {gl_cells[k]} tasks')

lines.append(f'\n=== Grade|Level|Subtopic cells: {len(glt_cells)} ===')
for k in sorted(glt_cells.keys()):
    lines.append(f'  G{k[0]}|L{k[1]}|{k[2][:50]}: {glt_cells[k]} tasks')

# Show unique subtopics found
subtopics_found = set()
for (g, l, st) in glt_cells.keys():
    if st not in ('__MAPPED_FAILED__', '__GL_MISMATCH__'):
        subtopics_found.add(st)
lines.append(f'\nUnique subtopics found via mapping: {len(subtopics_found)}')
for st in sorted(subtopics_found)[:20]:
    lines.append(f'  {st}')

# Show tasks that failed mapping
failed = [(oid, g, l) for oid, (g, l, st) in glt_by_task.items() if st == '__MAPPED_FAILED__']
lines.append(f'\nTasks with failed mapping: {len(failed)}')
if failed:
    for oid, g, l in failed[:5]:
        lines.append(f'  {oid} G{g}|L{l}')

# Show tasks with grade/level mismatch
mismatched = [(oid, g, l) for oid, (g, l, st) in glt_by_task.items() if st == '__GL_MISMATCH__']
lines.append(f'Tasks with grade/level mismatch: {len(mismatched)}')

with open('_mapping_results.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f'Written {len(lines)} lines to _mapping_results.txt')
