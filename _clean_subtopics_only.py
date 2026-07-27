#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Extract only REAL mathematical subtopics, filtering out olympiad/competition noise."""
import json
import re

FILE = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_completed.json'

with open(FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Patterns that indicate garbage olympiad-name subtopics
GARBAGE_PATTERNS = [
    r'олимпиад', r'Formula[\s\w]*Unity', r'Kurchatov', r'Lomonosov',
    r'Турнир городов', r'ВсОШ', r'Курчатов', r'МФТИ', r'СПбГУ',
    r'Эйлера', r'Покори Воробьёвы', r'Физтех', r'Ломоносов',
    r'round\s+(qualifying|final)', r'round\s+\d+',
    r'shortlist', r'P\d+$', r'Сгенерированная олимпиадная',
    r'^Олимпиадная задача$',
]

def is_garbage(subtopic: str) -> bool:
    for pat in GARBAGE_PATTERNS:
        if re.search(pat, subtopic, re.IGNORECASE):
            return True
    return False

# Also track which themes contain ONLY garbage subtopics
theme_subtopic_map = {}
for entry in data:
    th = entry.get('theme', '').strip()
    st = entry.get('subtopic', '').strip()
    if not th or not st:
        continue
    if th not in theme_subtopic_map:
        theme_subtopic_map[th] = set()
    theme_subtopic_map[th].add(st)

# Find themes that are entirely garbage-free
clean_subtopics = set()
for entry in data:
    st = entry.get('subtopic', '').strip()
    if not st:
        continue
    if not is_garbage(st):
        clean_subtopics.add(st)

sorted_clean = sorted(clean_subtopics, key=lambda x: x.lower())

with open('clean_subtopics_only.txt', 'w', encoding='utf-8') as out:
    out.write(f"Всего уникальных подтем (только математические): {len(sorted_clean)}\n")
    out.write("=" * 80 + "\n")
    for i, s in enumerate(sorted_clean, 1):
        out.write(f"{i:3d}. {s}\n")

# Also show which garbage subtopics were removed
garbage_subtopics = set()
for entry in data:
    st = entry.get('subtopic', '').strip()
    if st and is_garbage(st):
        garbage_subtopics.add(st)

sorted_garbage = sorted(garbage_subtopics, key=lambda x: x.lower())
with open('clean_subtopics_only.txt', 'a', encoding='utf-8') as out:
    out.write("\n\n")
    out.write(f"ИСКЛЮЧЕНО (олимпиадный мусор): {len(sorted_garbage)}\n")
    out.write("=" * 80 + "\n")
    for i, s in enumerate(sorted_garbage, 1):
        out.write(f"{i:3d}. {s}\n")

print(f"Чистых подтем: {len(sorted_clean)}")
print(f"Исключено мусора: {len(sorted_garbage)}")
print(f"Всего: {len(sorted_clean) + len(sorted_garbage)}")
