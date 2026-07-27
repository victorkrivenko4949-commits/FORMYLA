#!/usr/bin/env python3
"""List all subtopics and subtopic cells for L1-L3 tasks."""
import json
from collections import defaultdict

bank = json.load(open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8'))

# All subtopics from L1-L3 tasks
subtopics = set()
topic_subtopics = defaultdict(set)
cells = defaultdict(list)

for t in bank:
    lv = str(t.get('level', ''))
    if lv in ('1', '2', '3'):
        sub = t.get('subtopic', '__NO_SUBTOPIC__') or '__NO_SUBTOPIC__'
        top = t.get('topic', 'NO_TOPIC') or 'NO_TOPIC'
        g = str(t.get('grade', '?')) or '?'
        cell_key = f'G{g}|L{lv}|{top}|{sub}'
        subtopics.add(sub)
        topic_subtopics[top].add(sub)
        cells[cell_key].append(t.get('original_id', '?'))

lines = []
lines.append(f'=== Все уникальные подтемы в L1-L3 ({len(subtopics)} всего) ===')
lines.append('')
for s in sorted(subtopics):
    lines.append(f'  {s}')

lines.append('')
lines.append(f'=== По темам ===')
lines.append('')
for top in sorted(topic_subtopics.keys()):
    subs = sorted(topic_subtopics[top])
    lines.append(f'  Тема: {top} ({len(subs)} подтем)')
    for s in subs:
        lines.append(f'    - {s}')

lines.append('')
lines.append(f'=== Все subtopic ячейки в L1-L3 ({len(cells)} всего) ===')
lines.append('')
for c in sorted(cells.keys()):
    lines.append(f'  {c}: {len(cells[c])} tasks')

with open('_all_l1l3_subtopics.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f'Written {len(subtopics)} subtopics, {len(cells)} cells to _all_l1l3_subtopics.txt')
