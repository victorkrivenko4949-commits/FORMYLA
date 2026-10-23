#!/usr/bin/env python3
"""Diagnose combo_id mismatch between the two JSONL files."""
import json

IMAGES_JSONL = "olympiad-db/public/data/FORMYLA_olympiad_DB_no_holes_with_images.jsonl"
MAIN_JSONL = "data/olympiads/olympiad_DB_final_fixed.jsonl"

print("=" * 70)
print("DIAG: Combo ID alignment between images JSONL and main JSONL")
print("=" * 70)

# Read images JSONL
images_by_id = {}
with open(IMAGES_JSONL, 'r', encoding='utf-8') as f:
    for line in f:
        c = json.loads(line.strip())
        cid = c.get('id')
        if cid:
            images_by_id[str(cid)] = {
                'olympiad': c.get('olympiad'),
                'year': c.get('year'),
                'grade': c.get('grade'),
                'round': c.get('round'),
                'num_problems': len(c.get('problems', [])),
                'has_images': any(p.get('images') for p in c.get('problems', []))
            }

print(f"\nImages JSONL: {len(images_by_id)} entries with IDs")

# Read main JSONL
main_by_id = {}
with open(MAIN_JSONL, 'r', encoding='utf-8') as f:
    for line in f:
        c = json.loads(line.strip())
        cid = c.get('id')
        if cid:
            main_by_id[str(cid)] = {
                'olympiad': c.get('olympiad'),
                'year': c.get('year'),
                'grade': c.get('grade'),
                'round': c.get('round'),
                'num_problems': len(c.get('problems', []))
            }

print(f"Main JSONL:   {len(main_by_id)} entries with IDs")

# Compare ID sets
img_ids = set(images_by_id.keys())
main_ids = set(main_by_id.keys())

common = img_ids & main_ids
only_img = img_ids - main_ids
only_main = main_ids - img_ids

print(f"\nCommon IDs:     {len(common)}")
print(f"Only in images: {len(only_img)}")
print(f"Only in main:   {len(only_main)}")

# Check common IDs for metadata mismatches
print("\n" + "-" * 70)
print("Checking common IDs for (slug, year) mismatches:")
print("-" * 70)
mismatches = 0
for cid in sorted(common, key=lambda x: int(x) if x.isdigit() else 0):
    img = images_by_id[cid]
    main = main_by_id[cid]
    slug_match = (img['olympiad'] or '').strip() == (main['olympiad'] or '').strip()
    year_match = str(img['year'] or '') == str(main['year'] or '')
    if not slug_match or not year_match:
        mismatches += 1
        flag = " *** MISMATCH ***" if not slug_match else ""
        print(f"  id={cid}: IMG={img['olympiad']}/{img['year']} g={img['grade']} r={img['round']}")
        print(f"          MAIN={main['olympiad']}/{main['year']} g={main['grade']} r={main['round']}{flag}")

if mismatches == 0:
    print("  All common IDs match on (olympiad slug, year)!")
else:
    print(f"\n  Total mismatches: {mismatches}")

# Show entries only in images JSONL (that have images)
print("\n" + "-" * 70)
print("Entries ONLY in images JSONL (that have images):")
print("-" * 70)
count_img = 0
for cid in sorted(only_img, key=lambda x: int(x) if x.isdigit() else 0):
    img = images_by_id[cid]
    if img['has_images'] and count_img < 15:
        print(f"  id={cid}: {img['olympiad']}/{img['year']} g={img['grade']} r={img['round']} ({img['num_problems']} probs)")
        count_img += 1
if count_img == 0:
    print("  (none with images)")

# Show entries only in main JSONL
print("\n" + "-" * 70)
print("Entries ONLY in main JSONL (first 15):")
print("-" * 70)
count_main = 0
for cid in sorted(only_main, key=lambda x: int(x) if x.isdigit() else 0):
    main = main_by_id[cid]
    if count_main < 15:
        print(f"  id={cid}: {main['olympiad']}/{main['year']} g={main['grade']} r={main['round']} ({main['num_problems']} probs)")
        count_main += 1

# Show Euler entries specifically
print("\n" + "-" * 70)
print("EULER entries in BOTH JSONLs (compared by id):")
print("-" * 70)
for cid in sorted(common, key=lambda x: int(x) if x.isdigit() else 0):
    img = images_by_id[cid]
    main = main_by_id[cid]
    if img['olympiad'] == 'euler' or main['olympiad'] == 'euler':
        match = "OK" if (img['olympiad'] == main['olympiad'] and str(img['year']) == str(main['year'])) else "MISMATCH"
        print(f"  id={cid}: IMG={img['olympiad']}/{img['year']} g={img['grade']} r={img['round']}")
        print(f"          MAIN={main['olympiad']}/{main['year']} g={main['grade']} r={main['round']} [{match}]")
        if img['has_images']:
            print(f"          -> HAS IMAGES in images JSONL")

print("\nEULER entries ONLY in images JSONL:")
for cid in sorted(only_img, key=lambda x: int(x) if x.isdigit() else 0):
    img = images_by_id[cid]
    if img['olympiad'] == 'euler':
        print(f"  id={cid}: year={img['year']} g={img['grade']} r={img['round']} ({img['num_problems']} probs, has_images={img['has_images']})")

print("\nEULER entries ONLY in main JSONL:")
for cid in sorted(only_main, key=lambda x: int(x) if x.isdigit() else 0):
    main = main_by_id[cid]
    if main['olympiad'] == 'euler':
        print(f"  id={cid}: year={main['year']} g={main['grade']} r={main['round']} ({main['num_problems']} probs)")

print("\nDone.")
