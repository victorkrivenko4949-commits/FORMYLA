#!/usr/bin/env python3
"""Generate IMAGE_MAP entries for problem_images/*.png files."""
import json, os, sys

JSONL_PATH = r'C:\Users\Victor\Downloads\olympiad_DB_final_fixed.jsonl'
IMG_DIR = 'static/problem_images'

# Load all JSONL entries
combos_by_key = {}
with open(JSONL_PATH, 'r', encoding='utf-8') as f:
    for line in f:
        entry = json.loads(line)
        key = (entry.get('olympiad',''), str(entry.get('year','')), str(entry.get('grade','')))
        if key not in combos_by_key:
            combos_by_key[key] = []
        combos_by_key[key].append(entry)

print(f"Loaded {len(combos_by_key)} unique (olympiad,year,grade) keys")

# Scan images
if not os.path.isdir(IMG_DIR):
    print(f"ERROR: Directory {IMG_DIR} not found!")
    sys.exit(1)

images = sorted([f for f in os.listdir(IMG_DIR) if f.endswith('.png')])
print(f"Found {len(images)} images in problem_images/\n")

for img in images:
    parts = img.replace('.png','').split('_')
    year = parts[-3]
    grade = parts[-2]
    num = int(parts[-1])
    olympiad = '_'.join(parts[:-3])
    
    size_kb = os.path.getsize(os.path.join(IMG_DIR, img)) // 1024
    
    candidates = combos_by_key.get((olympiad, year, grade), [])
    print(f"  {img} ({size_kb} KB) -> o={olympiad} y={year} g={grade} n={num} candidates={len(candidates)}")
    
    matched = None
    for c in candidates:
        problems = c.get('problems', [])
        for p in problems:
            pnum = p.get('num')
            if pnum == num:
                matched = c
                break
        if matched:
            break
    
    if matched:
        combo_id = matched.get('id')
        round_key = matched.get('round', '')
        print(f"    MATCH: combo_id={combo_id}, round={round_key}")
        print(f"    ENTRY: ({combo_id}, {num}): \"problem_images/{img}\",")
    else:
        print(f"    NO MATCH")

print(f"\nDone.")
