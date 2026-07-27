#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Merge L1-L3 from adaptive_full_9120_fixed.json + L4-L5 from curated_bank_L1_L5_fixed.json
into a new 5-level file.

Usage:
    python _merge_adaptive_curated.py
"""
import json
import os
import shutil
from collections import Counter

ADAPTIVE = "adaptive_data/adaptive_full_9120_fixed.json"
CURATED = "curated_bank_L1_L5_fixed.json"
OUTPUT = "adaptive_data/adaptive_full_9120_fixed.json"  # overwrite the original after backup
BACKUP = "adaptive_data/adaptive_full_9120_fixed_BEFORE_MERGE.json"

# 1. Load adaptive (8 levels)
print("Loading adaptive_full_9120_fixed.json...")
adaptive_tasks = json.load(open(ADAPTIVE, 'r', encoding='utf-8'))
print(f"  Total: {len(adaptive_tasks)} tasks")

# 2. Filter L1-L3 from adaptive
l1_l3_from_adaptive = [t for t in adaptive_tasks if str(t.get('level', '')).strip() in ('1', '2', '3')]
print(f"  L1-L3 from adaptive: {len(l1_l3_from_adaptive)} tasks")
from collections import Counter
print(f"    By level: {dict(sorted(Counter(str(t.get('level','?')) for t in l1_l3_from_adaptive).items()))}")

# 3. Load curated (5 levels)
print("\nLoading curated_bank_L1_L5_fixed.json...")
curated_tasks = json.load(open(CURATED, 'r', encoding='utf-8'))
print(f"  Total: {len(curated_tasks)} tasks")

# 4. Filter L4-L5 from curated
l4_l5_from_curated = [t for t in curated_tasks if str(t.get('level', '')).strip() in ('4', '5')]
print(f"  L4-L5 from curated: {len(l4_l5_from_curated)} tasks")
print(f"    By level: {dict(sorted(Counter(str(t.get('level','?')) for t in l4_l5_from_curated).items()))}")

# 5. Merge
merged = l1_l3_from_adaptive + l4_l5_from_curated
print(f"\nMerged total: {len(merged)} tasks")
print(f"  By level: {dict(sorted(Counter(str(t.get('level','?')) for t in merged).items()))}")

# 6. Backup original adaptive file
if os.path.exists(BACKUP):
    print(f"\nBackup already exists: {BACKUP}, skipping...")
else:
    shutil.copy2(ADAPTIVE, BACKUP)
    print(f"\nBackup saved to: {BACKUP}")

# 7. Write merged to OUTPUT
with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)
print(f"\nWritten {len(merged)} tasks to {OUTPUT}")

print("\nDone! Now the file contains only L1-L3 (from adaptive) + L4-L5 (from curated).")
print("Rename suggestion: adaptive_full_L1_L5_merged.json or similar.")
