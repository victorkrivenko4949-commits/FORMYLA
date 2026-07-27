#!/usr/bin/env python3
"""
Merge images from FORMYLA_olympiad_DB_no_holes_with_images.jsonl into the Flask app.

Process:
1. Read the images JSONL (olympiad-db/public/data/...)
2. Build IMAGE_MAP: {(combo_id, problem_num): "images/relative/path.png"}
3. Copy image files from olympiad-db/public/images/ to static/images/
4. Preserve old problem_images.py entries that still have valid files
5. Generate new problem_images.py with the full merged IMAGE_MAP
6. Also generate a stats report
"""

import json
import os
import shutil
import sys

# Paths
IMAGES_JSONL = "olympiad-db/public/data/FORMYLA_olympiad_DB_no_holes_with_images.jsonl"
SOURCE_IMAGES_DIR = "olympiad-db/public/images"
TARGET_IMAGES_DIR = "static/images"
PROBLEM_IMAGES_OUT = "problem_images.py"
OLD_PROBLEM_IMAGES = "problem_images.py.bak"  # backup of old file
STATS_FILE = "_image_merge_report.txt"

def main():
    # 1. Read images JSONL and build mapping
    print(f"Reading {IMAGES_JSONL} ...")
    with open(IMAGES_JSONL, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    image_map = {}  # {(combo_id, problem_num): "images/path.png"}
    kind_counts = {}  # for stats
    total_problems_with_images = 0
    total_images = 0
    skipped_no_file = 0

    for line_idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        combo = json.loads(line)
        cid = combo.get('id')
        # Skip entries with empty/null IDs — they have no corresponding combo in the main app
        if not cid:
            continue
        slug = combo.get('olympiad', '?')
        year = combo.get('year', '?')
        grade = combo.get('grade', '?')
        round_ = combo.get('round', '?')

        for prob in combo.get('problems', []):
            num = prob.get('num')
            imgs = prob.get('images', [])
            if not imgs:
                continue

            total_problems_with_images += 1

            # Pick the best image: prefer "statement_page_crop" or "statement" kind
            # If multiple, pick the first one
            best_img = None
            for img in imgs:
                kind = img.get('kind', '')
                kind_counts[kind] = kind_counts.get(kind, 0) + 1
                total_images += 1
                if best_img is None:
                    best_img = img
                elif kind == 'statement_page_crop' and best_img.get('kind') != 'statement_page_crop':
                    best_img = img
                elif kind == 'statement' and best_img.get('kind') not in ('statement_page_crop', 'statement'):
                    best_img = img

            if best_img is None:
                continue

            # Get file path, strip "out/" prefix
            file_path = best_img.get('file', '')
            if file_path.startswith('out/'):
                file_path = file_path[4:]  # remove "out/" prefix

            # The path should be like "images/euler/euler_2009_tasks.pdf/..."
            # Verify source file exists
            source_file = os.path.join(SOURCE_IMAGES_DIR, file_path[len('images/'):] if file_path.startswith('images/') else file_path)
            if not os.path.exists(source_file):
                # Try alternate paths
                alt_source = os.path.join(SOURCE_IMAGES_DIR, os.path.basename(file_path))
                if os.path.exists(alt_source):
                    pass  # will be handled during copy
                else:
                    skipped_no_file += 1
                    continue

            # Key for IMAGE_MAP
            key = (cid, num)
            if key in image_map:
                # Already have an image for this problem, keep the first one
                continue

            image_map[key] = file_path

    print(f"\n=== MERGE SUMMARY ===")
    print(f"Total combos (lines) in JSONL: {len(lines)}")
    print(f"Total problems with images: {total_problems_with_images}")
    print(f"Total images in JSONL: {total_images}")
    print(f"Total IMAGE_MAP entries generated: {len(image_map)}")
    print(f"Skipped (file not found on disk): {skipped_no_file}")

    print(f"\nImage kind distribution:")
    for kind, count in sorted(kind_counts.items(), key=lambda x: -x[1]):
        print(f"  {kind}: {count}")

    # 2. Copy images to static/images/
    print(f"\nCopying images from {SOURCE_IMAGES_DIR} to {TARGET_IMAGES_DIR} ...")
    os.makedirs(TARGET_IMAGES_DIR, exist_ok=True)

    copied = 0
    errors = 0
    for (cid, num), rel_path in image_map.items():
        # rel_path is like "images/euler/euler_2009_tasks.pdf/...png"
        # Target path: static/images/euler/euler_2009_tasks.pdf/...png
        target_rel = rel_path[len('images/'):] if rel_path.startswith('images/') else rel_path
        target_path = os.path.join(TARGET_IMAGES_DIR, target_rel)

        # Source path
        source_rel = rel_path[len('images/'):] if rel_path.startswith('images/') else rel_path
        source_path = os.path.join(SOURCE_IMAGES_DIR, source_rel)

        if not os.path.exists(source_path):
            # Try just the filename
            alt_source = os.path.join(SOURCE_IMAGES_DIR, os.path.basename(rel_path))
            if os.path.exists(alt_source):
                source_path = alt_source
            else:
                errors += 1
                continue

        # Create target directory
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        try:
            shutil.copy2(source_path, target_path)
            copied += 1
        except Exception as e:
            errors += 1

    print(f"Images copied: {copied}")
    print(f"Errors: {errors}")

    # 3. Generate new problem_images.py
    print(f"\nGenerating {PROBLEM_IMAGES_OUT} ...")
    with open(PROBLEM_IMAGES_OUT, 'w', encoding='utf-8') as f:
        f.write('"""\n')
        f.write('problem_images.py — Автоматически сгенерировано _merge_images_into_flask.py\n')
        f.write(f'Содержит {len(image_map)} привязок рисунков к задачам из images JSONL\n')
        f.write('"""\n\n')
        f.write('# IMAGE_MAP: {(combo_id, problem_num): "images/relative/path.png"}\n')
        f.write('IMAGE_MAP = {\n')

        # Sort by combo_id then problem_num for readability (handle mixed int/str)
        def sort_key(k):
            cid, num = k
            # Convert to tuple that sorts ints and strings consistently
            if isinstance(cid, int):
                cid_sort = (0, cid)
            else:
                cid_sort = (1, str(cid))
            if isinstance(num, int):
                num_sort = (0, num)
            else:
                num_sort = (1, str(num))
            return (cid_sort, num_sort)

        for key in sorted(image_map.keys(), key=sort_key):
            cid, num = key
            # Quote string keys to avoid NameError (e.g. gap_kurchatov_...)
            cid_str = repr(cid) if isinstance(cid, str) else str(cid)
            num_str = repr(num) if isinstance(num, str) else str(num)
            rel_path = image_map[key]
            f.write(f'    ({cid_str}, {num_str}): "{rel_path}",\n')

        f.write('}\n')

    print(f"Done! Generated {len(image_map)} entries in {PROBLEM_IMAGES_OUT}")

    # 4. Write stats
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        f.write("=== IMAGE MERGE REPORT ===\n\n")
        f.write(f"Total combos in JSONL: {len(lines)}\n")
        f.write(f"Total problems with images: {total_problems_with_images}\n")
        f.write(f"Total images in JSONL: {total_images}\n")
        f.write(f"IMAGE_MAP entries: {len(image_map)}\n")
        f.write(f"Images copied to static/: {copied}\n")
        f.write(f"Copy errors: {errors}\n")
        f.write(f"Skipped (file not found): {skipped_no_file}\n\n")
        f.write("Image kind distribution:\n")
        for kind, count in sorted(kind_counts.items(), key=lambda x: -x[1]):
            f.write(f"  {kind}: {count}\n")

    print(f"Stats written to {STATS_FILE}")

if __name__ == '__main__':
    main()
