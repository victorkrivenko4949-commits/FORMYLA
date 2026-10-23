#!/usr/bin/env python3
"""Comprehensive analysis of the source 1080 JSON."""
import json, hashlib, sys
from collections import Counter

SOURCE = r"C:\Users\Victor\Downloads\formyla_levels1_8_selection_1080.json"

with open(SOURCE, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total tasks: {len(data)}")
print(f"Top-level type: list")

# SHA-256
sha = hashlib.sha256()
with open(SOURCE, 'rb') as f:
    sha.update(f.read())
print(f"SHA-256: {sha.hexdigest()}")

# All field names
all_keys = set()
for t in data:
    all_keys.update(t.keys())
print(f"All field names: {sorted(all_keys)}")

# class_level distribution
cl = Counter(t.get('class_level') for t in data)
print(f"\nclass_level distribution:")
for c in sorted(cl):
    print(f"  class {c}: {cl[c]}")

# difficulty_level distribution
dl = Counter(t.get('difficulty_level') for t in data)
print(f"\ndifficulty_level distribution:")
for d in sorted(dl):
    print(f"  level {d}: {dl[d]}")

# Cross-tab class x difficulty
print(f"\nCross-tab: class_level x difficulty_level")
print(f"{'class':>6}", end='')
for l in range(1, 9):
    print(f" {f'dl{l}':>4}", end='')
print(f" {'total':>6}")

for c in sorted(set(t.get('class_level') for t in data)):
    print(f"{c:>6}", end='')
    row_total = 0
    for l in range(1, 9):
        cnt = sum(1 for t in data if t.get('class_level') == c and t.get('difficulty_level') == l)
        print(f" {cnt:>4}", end='')
        row_total += cnt
    print(f" {row_total:>6}")

# Total row
print(f"{'total':>6}", end='')
for l in range(1, 9):
    cnt = sum(1 for t in data if t.get('difficulty_level') == l)
    print(f" {cnt:>4}", end='')
print(f" {len(data):>6}")

# Image analysis
img_count = sum(1 for t in data if t.get('image'))
no_img_count = sum(1 for t in data if not t.get('image'))
print(f"\nTasks with image non-empty: {img_count}")
print(f"Tasks with empty image: {no_img_count}")

# Check for figures field
has_fig = sum(1 for t in data if 'figures' in t and t['figures'])
print(f"Tasks with figures field: {has_fig}")

# Check for id field
has_id = sum(1 for t in data if 'id' in t)
print(f"Tasks with 'id' field: {has_id}")

# Flagged
flagged = sum(1 for t in data if t.get('is_flagged'))
print(f"Flagged tasks: {flagged}")

# Topics
topics = Counter(t.get('topic', '') for t in data)
print(f"\nTopic distribution:")
for topic, cnt in topics.most_common(20):
    print(f"  [{cnt:>3}] {topic}")

# Sample first task
print(f"\n=== First task (index 0) ===")
print(json.dumps(data[0], ensure_ascii=False, indent=2))

# Sample mid task
print(f"\n=== Task at index 539 ===")
if len(data) > 539:
    print(json.dumps(data[539], ensure_ascii=False, indent=2))

# Last task
print(f"\n=== Last task (index {len(data)-1}) ===")
print(json.dumps(data[-1], ensure_ascii=False, indent=2))
