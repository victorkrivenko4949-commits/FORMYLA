#!/usr/bin/env python3
"""Verify that problem_images.py imports correctly and files exist."""
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

try:
    from problem_images import IMAGE_MAP
    print(f"OK: {len(IMAGE_MAP)} entries in IMAGE_MAP")
except Exception as e:
    print(f"ERROR importing problem_images: {e}")
    sys.exit(1)

# Check first entry
keys = list(IMAGE_MAP.keys())
first_key = keys[0]
first_val = IMAGE_MAP[first_key]
# The rel_path is like "images/euler/...png"
# Flask url_for('static', filename=rel_path) resolves to /static/images/euler/...png
# File on disk is at static/images/euler/...png
full_path = os.path.join('static', first_val)
print(f"First: key={first_key}")
print(f"  Value: {first_val}")
print(f"  Full path: {full_path}")
print(f"  File exists: {os.path.isfile(full_path)}")
if os.path.isfile(full_path):
    print(f"  File size: {os.path.getsize(full_path)} bytes")

# Check last entry (string-keyed)
last_key = keys[-1]
last_val = IMAGE_MAP[last_key]
full_path2 = os.path.join('static', last_val)
print(f"\nLast: key={last_key}")
print(f"  Value: {last_val}")
print(f"  File exists: {os.path.isfile(full_path2)}")

# Find a string-keyed entry with gap_
for k, v in IMAGE_MAP.items():
    if isinstance(k[0], str) and 'gap' in k[0]:
        full_path3 = os.path.join('static', v)
        print(f"\nString-keyed gap example: {k} -> {v}")
        print(f"  File exists: {os.path.isfile(full_path3)}")
        break

# Count files actually on disk
count = 0
for (cid, num), rel_path in IMAGE_MAP.items():
    full_path = os.path.join('static', rel_path)
    if os.path.isfile(full_path):
        count += 1

print(f"\nFiles on disk: {count} / {len(IMAGE_MAP)}")
print("ALL CHECKS PASSED" if count == len(IMAGE_MAP) else "WARNING: Some files missing!")
