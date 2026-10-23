# -*- coding: utf-8 -*-
"""Analyze all figure resources in the project."""
import json
import os
from collections import Counter

print("=" * 60)
print("1. SOLUTION FIGURES INDEX (data/solution_figures_index.json)")
print("=" * 60)
data = json.load(open('data/solution_figures_index.json', 'r', encoding='utf-8'))
print(f"Total keys: {len(data)}")

# Kurchatov entries
kurchatov = {k: v for k, v in data.items() if 'kurchatov' in k.lower()}
print(f"\n--- Kurchatov entries ({len(kurchatov)}) ---")
for k, v in sorted(kurchatov.items()):
    files = [f.get('file', '?') for f in v]
    print(f"  {k}: {files}")

# Summary by olympiad
c = Counter()
all_files = set()
for k, v in data.items():
    oly = k.split('|')[0]
    c[oly] += len(v)
    for f in v:
        fn = f.get('file', '')
        if fn:
            all_files.add(fn)

print(f"\n--- Figures by olympiad ---")
for oly, cnt in sorted(c.items()):
    print(f"  {oly}: {cnt} figure entries")
print(f"Total unique files referenced: {len(all_files)}")

# Show all unique files
print(f"\n--- All unique figure files ---")
for f in sorted(all_files):
    print(f"  {f}")

print("\n")
print("=" * 60)
print("2. PROBLEM IMAGES (problem_images.py IMAGE_MAP)")
print("=" * 60)
# Parse IMAGE_MAP
from problem_images import IMAGE_MAP
print(f"Total IMAGE_MAP entries: {len(IMAGE_MAP)}")

# Group by olympiad
oly_images = Counter()
for (combo_id, prob_num), path in IMAGE_MAP.items():
    if 'kurchatov' in path.lower():
        print(f"  KURCHATOV: combo_id={combo_id}, prob={prob_num}, path={path}")
    # Determine olympiad from path
    parts = path.replace('\\', '/').split('/')
    if 'problem_images' in parts:
        fn = parts[-1]
        oly_name = fn.split('_')[0]
    elif len(parts) >= 2:
        oly_name = parts[-2] if parts[-2] != 'olympiads' else parts[-3]
    else:
        oly_name = 'unknown'
    oly_images[oly_name] += 1

print("\n--- Images by olympiad ---")
for oly, cnt in sorted(oly_images.items()):
    print(f"  {oly}: {cnt} images")
print(f"Total: {len(IMAGE_MAP)} images")

print("\n")
print("=" * 60)
print("3. GEOMETRY DRAWINGS (static/img/vsosh9_geometry/)")
print("=" * 60)
geo_dir = 'static/img/vsosh9_geometry'
if os.path.isdir(geo_dir):
    svg_files = [f for f in os.listdir(geo_dir) if f.endswith('.svg')]
    print(f"Total SVG files: {len(svg_files)}")
    # Group by method code
    methods = Counter()
    for f in svg_files:
        code = f.split('_')[0]  # e.g. F1
        methods[code] += 1
    for code, cnt in sorted(methods.items()):
        print(f"  {code}: {cnt} files")
else:
    print(f"  Directory not found: {geo_dir}")

print("\n")
print("=" * 60)
print("4. PROBLEM IMAGES FILES (static/problem_images/)")
print("=" * 60)
pi_dir = 'static/problem_images'
if os.path.isdir(pi_dir):
    pi_files = sorted(os.listdir(pi_dir))
    print(f"Total files: {len(pi_files)}")
    for f in pi_files:
        print(f"  {f}")
else:
    print(f"  Directory not found: {pi_dir}")

print("\n")
print("=" * 60)
print("5. IMAGES FROM static/images/problems/")
print("=" * 60)
probs_dir = 'static/images/problems'
if os.path.isdir(probs_dir):
    prob_files = sorted(os.listdir(probs_dir))
    print(f"Total files: {len(prob_files)}")
    # Count unique base names (ignoring copies)
    base_names = set()
    for f in prob_files:
        base = f.rsplit(' — копия', 1)[0]
        base_names.add(base)
    print(f"Unique base images: {len(base_names)}")
    # Group by olympiad
    oly_groups = Counter()
    for f in base_names:
        parts = f.split('_')
        if parts:
            oly_groups[parts[0]] += 1
    for oly, cnt in sorted(oly_groups.items()):
        print(f"  {oly}: {cnt} images")
else:
    print(f"  Directory not found: {probs_dir}")

print("\nDone!")
