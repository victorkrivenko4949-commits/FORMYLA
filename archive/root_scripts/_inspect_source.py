#!/usr/bin/env python3
"""Inspect the source JSON schema and structure."""
import json, sys, os, hashlib

# Try both possible paths
paths = [
    r"C:\Users\Victor\Downloads\formyla_levels1_8_selection_1080.json",
    r"C:\Users\Victor\Downloads\formyla_levels1_8_selection_1080 (1).json"
]

for p in paths:
    if os.path.exists(p):
        SOURCE = p
        print(f"Using source: {SOURCE}")
        break
else:
    print("ERROR: Source file not found!")
    sys.exit(1)

# Load
with open(SOURCE, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"\n=== SOURCE FILE OVERVIEW ===")
print(f"Full path: {os.path.abspath(SOURCE)}")
print(f"Size: {os.path.getsize(SOURCE):,} bytes")

# SHA-256
sha256 = hashlib.sha256()
with open(SOURCE, 'rb') as f:
    sha256.update(f.read())
print(f"SHA-256: {sha256.hexdigest()}")

# Type
print(f"\nTop-level type: {type(data).__name__}")

if isinstance(data, dict):
    print(f"Top-level keys: {list(data.keys())}")
    # Check for tasks array
    for k, v in data.items():
        if isinstance(v, list):
            print(f"  '{k}' is a list of {len(v)} items")
        elif isinstance(v, dict):
            print(f"  '{k}' is a dict with keys: {list(v.keys())[:20]}")
        else:
            print(f"  '{k}': {type(v).__name__} = {str(v)[:200]}")
    
    # Find the task list
    tasks = None
    for k, v in data.items():
        if isinstance(v, list):
            tasks = v
            task_key = k
            break
    
    if tasks is None:
        print("\nNo list found at top level, checking nested values...")
        for k, v in data.items():
            if isinstance(v, dict):
                for k2, v2 in v.items():
                    if isinstance(v2, list):
                        tasks = v2
                        task_key = f"{k}.{k2}"
                        print(f"Found list at '{task_key}' with {len(tasks)} items")
                        break
                if tasks:
                    break

elif isinstance(data, list):
    tasks = data
    task_key = "root array"

if tasks:
    print(f"\n=== TASK LIST ===")
    print(f"Key: {task_key}")
    print(f"Total items: {len(tasks)}")
    
    # First task schema
    t0 = tasks[0]
    print(f"\nFirst item type: {