#!/usr/bin/env python3
"""Diagnostic: inspect the selection_1080 snapshot to find how SEL1080-xxxx maps to hex task_ids."""

import json

SNAP_PATH = r"C:\Users\Victor\Downloads\FORMYLA_CONDITION_COURT\inputs\selection_1080\formyla_levels1_8_selection_1080_snapshot.json"

with open(SNAP_PATH, "r", encoding="utf-8") as f:
    tasks = json.load(f)

print(f"Total tasks in snapshot: {len(tasks)}")
print(f"Type of tasks: {type(tasks)}")

# First task keys
t0 = tasks[0]
print(f"\nFirst task keys ({len(t0)}):")
for k in t0:
    v = t0[k]
    if isinstance(v, str) and len(v) > 80:
        v = v[:80] + "..."
    print(f"  {k}: {repr(v)}")

# Check for any id/task_id fields that might contain hex IDs
id_candidates = []
for k in t0.keys():
    kl = k.lower()
    if "id" in kl or "uuid" in kl or "hash" in kl or "key" in kl or "uid" in kl:
        id_candidates.append(k)

print(f"\nCandidate ID fields: {id_candidates}")
for k in id_candidates:
    print(f"  {k}: {repr(t0[k])}")

# Check what fields the snapshot has vs what curated bank has  
# Look for a few IDs to see pattern
print("\n--- Sample IDs (first 5) ---")
for i in range(min(5, len(tasks))):
    t = tasks[i]
    oid = t.get("original_id", "N/A") if "original_id" in t else "N/A"
    idx = t.get("source_index", "N/A") if "source_index" in t else "N/A"
    print(f"  [{i}] original_id={oid}, source_index={idx}")

# Check if any task has an 'id' field that looks like a hex task_id (12 chars)
print("\n--- Searching for hex ID fields ---")
hex_fields = set()
for t in tasks[:100]:  # Check first 100
    for k, v in t.items():
        if isinstance(v, str) and len(v) in (12, 13, 24, 32, 36, 40) and all(c in "0123456789abcdef" for c in v.lower()):
            hex_fields.add(k)
            print(f"  Found hex-like field: {k} = {v}")

if not hex_fields:
    print("  No hex-like ID fields found in first 100 tasks. Checking all fields more broadly...")
    # Show ALL keys present in ANY task
    all_keys = set()
    for t in tasks:
        all_keys.update(t.keys())
    print(f"  All keys across all tasks: {sorted(all_keys)}")

# Check if there's an 'id' field at the top level
print("\n--- Checking for 'id' field ---")
has_id = sum(1 for t in tasks if "id" in t)
has_task_id = sum(1 for t in tasks if "task_id" in t)
has_taskid = sum(1 for t in tasks if "taskId" in t or "taskid" in t)
print(f"  tasks with 'id' field: {has_id}/{len(tasks)}")
print(f"  tasks with 'task_id' field: {has_task_id}/{len(tasks)}")

if has_id > 0:
    print(f"  Sample 'id' values:")
    for i in range(min(5, len(tasks))):
        print(f"    [{i}]: {tasks[i].get('id')}")

# Check if tasks might be nested
print("\n--- Checking for nested structure ---")
for i, t in enumerate(tasks[:5]):
    for k, v in t.items():
        if isinstance(v, (dict, list)):
            print(f"  [{i}] {k} is {type(v).__name__} of length {len(v) if isinstance(v, (list, dict)) else 'N/A'}")

# Check for any fields with 'original' or 'source' in name
print("\n--- Fields with 'original' or 'source' or 'task' ---")
for k in sorted(t0.keys()):
    kl = k.lower()
    if "origin" in kl or "source" in kl or "task" in kl:
        print(f"  {k}: {repr(t0[k])[:100]}")
