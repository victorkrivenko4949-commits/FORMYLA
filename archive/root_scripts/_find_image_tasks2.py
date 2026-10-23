#!/usr/bin/env python3
"""Find olympiad tasks with image files attached."""
import json, os, sys, re

JSONL_PATH = r'C:\Users\Victor\Downloads\olympiad_DB_final_fixed.jsonl'

# Collect all image filenames from static/images/problems
IMG_DIR = os.path.join('static', 'temp_unpack', 'images_package', 'static', 'images', 'problems')
image_files = set()
if os.path.isdir(IMG_DIR):
    for fname in os.listdir(IMG_DIR):
        if fname.endswith('.png'):
            image_files.add(fname)

print(f"Found {len(image_files)} image files in static/images/problems/")
if image_files:
    print(f"Sample: {sorted(list(image_files))[:5]}")

# Now search JSONL for references to these images
count = 0
with open(JSONL_PATH, 'r', encoding='utf-8') as f:
    for line in f:
        entry = json.loads(line)
        entry_id = entry.get('id', '')
        olympiad = entry.get('olympiad', '')
        olympiad_title = entry.get('olympiad_title', '')
        
        problems = entry.get('problems', [])
        for pi, problem in enumerate(problems):
            if isinstance(problem, dict):
                text = json.dumps(problem, ensure_ascii=False)
                # Check for image field directly
                if 'image' in problem or 'image_url' in problem or 'img' in problem:
                    img_val = problem.get('image') or problem.get('image_url') or problem.get('img')
                    print(f"\n=== DIRECT IMAGE FIELD ===")
                    print(f"Entry {entry_id}, olympiad={olympiad}, problem #{pi}")
                    print(f"Image: {img_val}")
                    print(f"Problem text: {str(problem.get('text',''))[:200]}")
                    count += 1
            elif isinstance(problem, str):
                text = problem
            else:
                text = str(problem)
            
            # Check if any image filename appears in text/solution
            for img_fname in image_files:
                if img_fname in text:
                    print(f"\n=== IMAGE REFERENCE IN TEXT ===")
                    print(f"Entry {entry_id}, olympiad={olympiad}, problem #{pi}")
                    print(f"Image: {img_fname}")
                    print(f"Text: {text[:300]}")
                    count += 1
                    break

# Also check for any problem with 'image' key in its dict structure
print(f"\n--- Checking problem structure for image fields ---")
with open(JSONL_PATH, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if i > 50:  # check first 50 entries
            break
        entry = json.loads(line)
        problems = entry.get('problems', [])
        for pi, problem in enumerate(problems):
            if isinstance(problem, dict):
                keys_with_img = [k for k in problem.keys() if any(x in k.lower() for x in ['img', 'pic', 'image', 'photo', 'рис', 'fig', 'draw'])]
                if keys_with_img:
                    print(f"Entry {entry.get('id')}, problem #{pi}: image-related keys = {keys_with_img}")

# Also check for image references in JSONL text (e.g. markdown image syntax, HTML img tags)
print(f"\n--- Searching for markdown/HTML image syntax ---")
img_pattern = re.compile(r'(!\[.*?\]\(.*?\)|<img[^>]*src\s*=\s*["\']([^"\']+)["\']|https?://\S+\.(?:png|jpg|jpeg|gif|svg))', re.IGNORECASE)
img_count = 0
with open(JSONL_PATH, 'r', encoding='utf-8') as f:
    for line in f:
        entry = json.loads(line)
        problems = entry.get('problems', [])
        for pi, problem in enumerate(problems):
            if isinstance(problem, dict):
                for field_name, field_val in problem.items():
                    if isinstance(field_val, str) and img_pattern.search(field_val):
                        matches = img_pattern.findall(field_val)
                        print(f"Entry {entry.get('id')}, olympiad={entry.get('olympiad')}, problem #{pi}, field '{field_name}': {matches[:3]}")
                        img_count += 1
            elif isinstance(problem, str) and img_pattern.search(problem):
                matches = img_pattern.findall(problem)
                print(f"Entry {entry.get('id')}, olympiad={entry.get('olympiad')}, problem #{pi} (string): {matches[:3]}")
                img_count += 1

if img_count == 0:
    print("No markdown/HTML image references found in text fields.")

if count == 0 and img_count == 0:
    print("\nNo tasks with image files directly attached to problems were found.")
    print("The images in static/temp_unpack/ may not be linked from the JSONL data yet.")
