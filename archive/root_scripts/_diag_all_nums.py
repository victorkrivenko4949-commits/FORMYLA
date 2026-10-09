#!/usr/bin/env python3
"""Check num values for ALL olympiads, not just euler."""
import json

MAIN_JSONL = "data/olympiads/olympiad_DB_final_fixed.jsonl"
IMAGES_JSONL = "olympiad-db/public/data/FORMYLA_olympiad_DB_no_holes_with_images.jsonl"

print("Comparing num values for ALL common IDs...")

# Load main JSONL nums
main_nums = {}
with open(MAIN_JSONL, 'r', encoding='utf-8') as f:
    for line in f:
        c = json.loads(line.strip())
        cid = c.get('id')
        if cid:
            main_nums[cid] = {
                'slug': c.get('olympiad'),
                'year': c.get('year'),
                'nums': [p.get('num') for p in c.get('problems', [])]
            }

# Load images JSONL nums
img_nums = {}
with open(IMAGES_JSONL, 'r', encoding='utf-8') as f:
    for line in f:
        c = json.loads(line.strip())
        cid = c.get('id')
        if cid:
            img_nums[cid] = {
                'slug': c.get('olympiad'),
                'year': c.get('year'),
                'nums': [p.get('num') for p in c.get('problems', [])]
            }

# Find common IDs
common = set(main_nums.keys()) & set(img_nums.keys())
print(f"Common IDs: {len(common)}")

diffs = []
for cid in sorted(common, key=lambda x: int(x) if isinstance(x, int) or (isinstance(x, str) and x.isdigit()) else str(x)):
    m = main_nums[cid]['nums']
    i = img_nums[cid]['nums']
    if m != i:
        diffs.append((cid, main_nums[cid], img_nums[cid]))
        print(f"\nDIFFER id={cid}:")
        print(f"  MAIN ({main_nums[cid]['slug']}/{main_nums[cid]['year']}): nums={m}")
        print(f"  IMG  ({img_nums[cid]['slug']}/{img_nums[cid]['year']}): nums={i}")

if not diffs:
    print("  All common IDs have matching num values!")
else:
    print(f"\nTotal differences: {len(diffs)}")

print("\nDone.")
