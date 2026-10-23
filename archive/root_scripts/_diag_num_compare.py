#!/usr/bin/env python3
"""Compare problem num values between images JSONL and main JSONL."""
import json

MAIN_JSONL = "data/olympiads/olympiad_DB_final_fixed.jsonl"
IMAGES_JSONL = "olympiad-db/public/data/FORMYLA_olympiad_DB_no_holes_with_images.jsonl"

print("=" * 70)
print("DIAG: Comparing problem num fields between JSONLs")
print("=" * 70)

# Check specific case: id=2
print("\n--- MAIN JSONL: id=2 ---")
with open(MAIN_JSONL, 'r', encoding='utf-8') as f:
    for line in f:
        c = json.loads(line.strip())
        if c.get('id') == 2:
            print(f"  olympiad={c.get('olympiad')}, year={c.get('year')}, grade={c.get('grade')}, round={c.get('round')}")
            print(f"  problems count: {len(c.get('problems',[]))}")
            for p in c.get('problems', []):
                print(f"    num={p.get('num')!r}, has_text={bool(p.get('text'))}, has_solution={bool(p.get('solution'))}")
            break

print("\n--- IMAGES JSONL: id=2 ---")
with open(IMAGES_JSONL, 'r', encoding='utf-8') as f:
    for line in f:
        c = json.loads(line.strip())
        if c.get('id') == 2:
            print(f"  olympiad={c.get('olympiad')}, year={c.get('year')}, grade={c.get('grade')}, round={c.get('round')}")
            for p in c.get('problems', []):
                imgs = p.get('images', [])
                fnames = [i.get('file','').split('/')[-1] for i in imgs]
                print(f"    num={p.get('num')!r}, images={fnames}")
            break

# Comprehensive check: compare num values for ALL common euler IDs
print("\n--- Euler entries: num value comparison ---")
main_nums = {}
with open(MAIN_JSONL, 'r', encoding='utf-8') as f:
    for line in f:
        c = json.loads(line.strip())
        if c.get('olympiad') == 'euler':
            main_nums[c.get('id')] = [p.get('num') for p in c.get('problems', [])]

img_nums = {}
with open(IMAGES_JSONL, 'r', encoding='utf-8') as f:
    for line in f:
        c = json.loads(line.strip())
        if c.get('olympiad') == 'euler':
            img_nums[c.get('id')] = [p.get('num') for p in c.get('problems', [])]

all_ids = sorted(set(list(main_nums.keys()) + list(img_nums.keys())), key=lambda x: int(x) if isinstance(x, int) or (isinstance(x, str) and x.isdigit()) else str(x))
for cid in all_ids:
    m = main_nums.get(cid, [])
    i = img_nums.get(cid, [])
    ok = "OK" if m == i else "DIFFER"
    print(f"  id={cid}: main nums={m}")
    print(f"          img  nums={i}  [{ok}]")

# Also check what the IMAGE_MAP actually contains for euler
print("\n--- IMAGE_MAP euler entries ---")
from problem_images import IMAGE_MAP
euler_map = {k: v for k, v in IMAGE_MAP.items() if 'euler' in v}
for key in sorted(euler_map.keys(), key=lambda x: (str(x[0]), str(x[1]))):
    cid, num = key
    print(f"  ({cid}, {num}) -> {euler_map[key]}")
print(f"\nTotal euler IMAGE_MAP entries: {len(euler_map)}")

print("\nDone.")
