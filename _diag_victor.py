#!/usr/bin/env python
"""Quick diagnosis of victor49.1-5.json and BEFORE_MERGE.json"""
import json
from collections import defaultdict, Counter

with open('adaptive_data/victor49.1-5.json', 'r', encoding='utf-8') as f:
    merged = json.load(f)

print("=== VICTOR49.1-5.JSON ===")
print(f"Total: {len(merged)}")
print(f"Keys of first task: {list(merged[0].keys())}")
print(f"Level: {merged[0].get('level')}")
print(f"subtopic: {repr(merged[0].get('subtopic', ''))}")
print(f"subject: {repr(merged[0].get('subject', ''))}")
print(f"topic: {repr(merged[0].get('topic', ''))}")
print(f"section: {repr(merged[0].get('section', ''))}")

levels = defaultdict(int)
for t in merged:
    levels[str(t.get('level', ''))] += 1
print(f"Levels: {dict(sorted(levels.items()))}")

# Check curated_bank subtopic field
print("\n=== CURATED_BANK_L1_L5_FIXED.JSON ===")
with open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8') as f:
    curated = json.load(f)
print(f"Total: {len(curated)}")
print(f"Keys: {list(curated[0].keys()) if curated else 'empty'}")
# Check if curated has topic or subtopic
for key in ['subtopic', 'topic', 'section', 'category']:
    vals = set(t.get(key, '') for t in curated)
    print(f"  {key}: {len(vals)} unique, empty={sum(1 for t in curated if not t.get(key,''))}")

# Check BEFORE_MERGE section/topic
print("\n=== BEFORE_MERGE SECTION & TOPIC ===")
with open('adaptive_data/adaptive_full_9120_fixed_BEFORE_MERGE.json', 'r', encoding='utf-8') as f:
    before = json.load(f)
print(f"Total: {len(before)}")
print(f"Keys: {list(before[0].keys())}")
for key in ['subtopic', 'topic', 'section']:
    vals = set(t.get(key, '') for t in before)
    print(f"  {key}: {len(vals)} unique, empty={sum(1 for t in before if not t.get(key,''))}")

# SECTION analysis per level
print("\n=== SECTION VALUES PER LEVEL ===")
for lvl in ['1','2','3']:
    lvl_tasks = [t for t in before if str(t.get('level',''))==lvl]
    sections = Counter(t.get('section','') for t in lvl_tasks)
    print(f"L{lvl} ({len(lvl_tasks)} tasks): {len(sections)} unique sections")
    for s,c in sections.most_common(15):
        print(f"  {repr(s)}: {c}")

# Cell balance with subject+section (NOT subtopic which is always empty)
print("\n=== CELL BALANCE (subject+section, since subtopic is always empty) ===")
for lvl in ['1','2','3']:
    lvl_tasks = [t for t in before if str(t.get('level',''))==lvl]
    cells = defaultdict(list)
    for t in lvl_tasks:
        cells[f"{t.get('subject','')}_{t.get('section','')}"].append(t)
    print(f"L{lvl}: {len(cells)} cells")
    ok = sum(1 for v in cells.values() if len(v)==5)
    over = sum(1 for v in cells.values() if len(v)>5)
    under = sum(1 for v in cells.values() if len(v)<5)
    print(f"  OK(5): {ok}, Over: {over}, Under: {under}")
    if over:
        print(f"  Top overfilled:")
        for k,v in sorted(cells.items(), key=lambda x: len(x[1]), reverse=True)[:5]:
            print(f"    {k}: {len(v)}")
