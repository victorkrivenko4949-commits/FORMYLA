#!/usr/bin/env python3
"""Diagnose which images are assigned to which problems vs expected."""
import json
import sys

IMAGES_JSONL = "olympiad-db/public/data/FORMYLA_olympiad_DB_no_holes_with_images.jsonl"
MAIN_JSONL = "data/olympiads/olympiad_DB_final_fixed.jsonl"

# 1. Read images JSONL - what num values exist?
print("=== IMAGES JSONL: problem 'num' values ===")
num_counts = {}
sample_by_olympiad = {}
with open(IMAGES_JSONL, 'r', encoding='utf-8') as f:
    for line in f:
        combo = json.loads(line.strip())
        cid = combo.get('id')
        if not cid:
            continue
        slug = combo.get('olympiad', '?')
        for prob in combo.get('problems', []):
            num = prob.get('num')
            num_counts[num] = num_counts.get(num, 0) + 1
            if slug not in sample_by_olympiad and slug == 'euler':
                sample_by_olympiad[slug] = {
                    'id': cid,
                    'year': combo.get('year'),
                    'grade': combo.get('grade'),
                    'round': combo.get('round'),
                    'nums': [p.get('num') for p in combo.get('problems', [])]
                }

for num, count in sorted(num_counts.items(), key=lambda x: str(x[0])):
    print(f"  num={num!r}: {count} problems")

print()
for slug, info in sample_by_olympiad.items():
    print(f"Olympiad {slug} (id={info['id']}): nums = {info['nums']}")

# 2. Read main JSONL - how are problems enumerated?
print("\n=== MAIN JSONL: problem enumeration ===")
main_by_id = {}
with open(MAIN_JSONL, 'r', encoding='utf-8') as f:
    for line in f:
        combo = json.loads(line.strip())
        cid = combo.get('id')
        if cid:
            main_by_id[str(cid)] = {
                'olympiad': combo.get('olympiad'),
                'year': combo.get('year'),
                'grade': combo.get('grade'),
                'round': combo.get('round'),
                'num_problems': len(combo.get('problems', []))
            }

# 3. For euler, print the IMAGE_MAP binding
print("\n=== EULER IMAGE_MAP bindings ===")
from problem_images import IMAGE_MAP
euler_entries = {k: v for k, v in IMAGE_MAP.items() if 'euler' in v}
for key in sorted(euler_entries.keys(), key=lambda x: (str(x[0]), str(x[1]))):
    cid, num = key
    print(f"  ({cid}, {num}) -> {euler_entries[key]}")

# 4. Check euler combo_id 1 in main JSONL
print("\n=== EULER (combo_id=1) in MAIN JSONL ===")
if '1' in main_by_id:
    info = main_by_id['1']
    print(f"  olympiad={info['olympiad']}, year={info['year']}, grade={info['grade']}, round={info['round']}")
    print(f"  num_problems={info['num_problems']}")
    
    # Check what IMAGE_MAP has for this
    for num in range(1, info['num_problems'] + 1):
        key = (1, num)
        if key in IMAGE_MAP:
            print(f"  Problem {num}: image={IMAGE_MAP[key]}")
        else:
            print(f"  Problem {num}: NO IMAGE")

# 5. Check images JSONL for euler combo_id 1
print("\n=== EULER (in images JSONL) ===")
with open(IMAGES_JSONL, 'r', encoding='utf-8') as f:
    for line in f:
        combo = json.loads(line.strip())
        cid = combo.get('id')
        if cid == 1 or str(cid) == '1':
            print(f"  id={cid}, slug={combo.get('olympiad')}, year={combo.get('year')}")
            for prob in combo.get('problems', []):
                num = prob.get('num')
                files = [img.get('file','') for img in prob.get('images',[])]
                print(f"    num={num!r}, images={files}")
            break
