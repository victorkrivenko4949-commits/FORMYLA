#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Extract flat list of all unique subtopics from the baseline file."""
import json

FILE = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_completed.json'

with open(FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

subtopics = set()
for entry in data:
    st = entry.get('subtopic', '').strip()
    if st:
        subtopics.add(st)

sorted_subs = sorted(subtopics, key=lambda x: x.lower())

with open('all_210_subtopics.txt', 'w', encoding='utf-8') as out:
    out.write(f"Всего уникальных подтем: {len(sorted_subs)}\n")
    out.write("=" * 80 + "\n")
    for i, s in enumerate(sorted_subs, 1):
        out.write(f"{i:3d}. {s}\n")

print(f"Записано {len(sorted_subs)} подтем в all_210_subtopics.txt")
