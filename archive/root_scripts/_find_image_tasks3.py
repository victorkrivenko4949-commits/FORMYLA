#!/usr/bin/env python3
"""Find fu (Физтех) olympiad entries and their problem structures."""
import json

JSONL_PATH = r'C:\Users\Victor\Downloads\olympiad_DB_final_fixed.jsonl'

# Find all "fu" entries
fu_entries = []
count = 0
with open(JSONL_PATH, 'r', encoding='utf-8') as f:
    for line in f:
        entry = json.loads(line)
        o = entry.get('olympiad', '')
        if o == 'fu':
            fu_entries.append(entry)
        count += 1

print(f"Total entries in JSONL: {count}")
print(f"Total 'fu' entries: {len(fu_entries)}")

if fu_entries:
    for entry in fu_entries[:5]:
        problems = entry.get('problems', [])
        print(f"\n--- fu entry id={entry.get('id')}, year={entry.get('year')}, grade={entry.get('grade')}, round={entry.get('round')} ---")
        print(f"  Problems count: {len(problems)}")
        for pi, p in enumerate(problems[:3]):
            if isinstance(p, dict):
                print(f"  Problem {pi}: keys={list(p.keys())}")
                print(f"    text: {str(p.get('text',''))[:150]}")
            else:
                print(f"  Problem {pi} (string): {str(p)[:150]}")

# Now check what "fu" image files exist
import os
IMG_DIR = os.path.join('static', 'temp_unpack', 'images_package', 'static', 'images', 'problems')
if os.path.isdir(IMG_DIR):
    fu_images = sorted([f for f in os.listdir(IMG_DIR) if f.startswith('fu_')])
    print(f"\nTotal fu images: {len(fu_images)}")
    # Parse image names: fu_YEAR_GRADE_figN.png
    from collections import defaultdict
    by_year_grade = defaultdict(list)
    for img in fu_images:
        # fu_2024_g5_fig1.png
        parts = img.replace('.png', '').split('_')
        # parts = ['fu', '2024', 'g5', 'fig1']
        year_grade = f"{parts[1]}_{parts[2]}"
        by_year_grade[year_grade].append(img)
    
    for yg, imgs in sorted(by_year_grade.items()):
        print(f"  {yg}: {len(imgs)} images -> {imgs}")

# Check if there's an images manifest or mapping somewhere
MANIFEST_PATHS = [
    'static/temp_unpack/images_package/',
    'static/images/',
    'data/',
]
for mp in MANIFEST_PATHS:
    if os.path.isdir(mp):
        files = os.listdir(mp)
        json_files = [f for f in files if f.endswith('.json')]
        if json_files:
            print(f"\nJSON files in {mp}: {json_files}")
