#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Patch _regenerated_675_tasks.json with 8 new successful retry results."""

import json
import sys

REGENERATED_FILE = "_regenerated_675_tasks.json"
RETRY_FILE = "_retry_8_final_results.json"

# Load regenerated tasks
print(f"Loading {REGENERATED_FILE}...")
with open(REGENERATED_FILE, "r", encoding="utf-8") as f:
    regen = json.load(f)

# Load retry results
print(f"Loading {RETRY_FILE}...")
with open(RETRY_FILE, "r", encoding="utf-8") as f:
    retry = json.load(f)

results = regen.get("results", [])
retry_results = retry.get("results", [])

# Build index by original_id
retry_map = {}
for r in retry_results:
    oid = r.get("original_id")
    if oid:
        retry_map[oid] = r

print(f"Retry results: {len(retry_results)}, keys: {list(retry_map.keys())}")

# Update matching entries
patched = 0
for i, entry in enumerate(results):
    oid = entry.get("original_id")
    if oid in retry_map:
        r = retry_map[oid]
        print(f"  [{i}] Patching {oid}...")
        entry["success"] = True
        entry["fixed_task"] = r["fixed_task"]
        entry["changes_made"] = r["changes_made"]
        entry["error"] = None
        entry["fixed_by_ai"] = True
        entry["fix_timestamp"] = "2026-07-15T17:25:28+00:00"
        patched += 1

# Update summary
total = len(results)
success_count = sum(1 for r in results if r.get("success"))
regen["summary"]["total_regenerated"] = success_count
regen["summary"]["total_failed"] = total - success_count
regen["summary"]["pipeline_complete"] = success_count == total

print(f"\nPatched {patched} entries")
print(f"Total: {total}, Success: {success_count}, Failed: {total - success_count}")

if patched > 0:
    print(f"\nWriting updated {REGENERATED_FILE}...")
    with open(REGENERATED_FILE, "w", encoding="utf-8") as f:
        json.dump(regen, f, ensure_ascii=False, indent=2)
    print("Done!")
else:
    print("WARNING: No entries patched! Check original_id matching.")
    # Show first few original_ids to debug
    print(f"First 3 results original_ids: {[r.get('original_id') for r in results[:3]]}")
    sys.exit(1)
