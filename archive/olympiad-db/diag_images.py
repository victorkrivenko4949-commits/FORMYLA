#!/usr/bin/env python3
"""Check image structure in JSONL data."""
import json, os

jsonl_path = os.path.join(os.path.dirname(__file__), 'public', 'data', 'FORMYLA_olympiad_DB_no_holes_with_images.jsonl')

with open(jsonl_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Total JSONL lines: {len(lines)}")

found_images = 0
total_problems_with_images = 0
first_example = None

for line_idx, line in enumerate(lines):
    obj = json.loads(line)
    olympiad = obj.get('olympiad', '?')
    year = obj.get('year', '?')
    grade = obj.get('grade', '?')
    
    for prob in obj.get('problems', []):
        images = prob.get('images')
        if images and len(images) > 0:
            total_problems_with_images += 1
            found_images += len(images)
            if first_example is None:
                first_example = {
                    'line': line_idx + 1,
                    'olympiad': olympiad,
                    'year': year,
                    'grade': grade,
                    'round': obj.get('round', '?'),
                    'problem_num': prob.get('num'),
                    'images': images
                }
                print(f"\n=== FIRST PROBLEM WITH IMAGES ===")
                print(f"JSONL line: {line_idx + 1}")
                print(f"Olympiad: {olympiad}, Year: {year}, Grade: {grade}")
                print(f"Problem num: {prob.get('num')}")
                print(f"Problem keys: {list(prob.keys())}")
                print(f"Images count: {len(images)}")
                for img in images:
                    print(f"  kind={img.get('kind')}, file={img.get('file')}, confidence={img.get('confidence')}")
                    # Also show ALL keys of the image object
                    print(f"  image keys: {list(img.keys())}")

print(f"\n=== SUMMARY ===")
print(f"Problems WITH images: {total_problems_with_images}")
print(f"Total image entries: {found_images}")

# Also check the specific Euler problem
print(f"\n=== CHECKING EULER 2009 G8 REGIONAL ===")
for line_idx, line in enumerate(lines):
    obj = json.loads(line)
    if (obj.get('olympiad') == 'euler' and 
        obj.get('year') == 2009 and 
        obj.get('grade') == 8 and 
        obj.get('round') == 'regional'):
        print(f"Found at line {line_idx + 1}")
        print(f"Problems count: {len(obj['problems'])}")
        for prob in obj['problems']:
            images = prob.get('images', [])
            print(f"  Problem #{prob.get('num')}: images={len(images)}, text_preview={prob.get('text','')[:80]}...")
            if images:
                print(f"    Image 0: {json.dumps(images[0], ensure_ascii=False)}")
