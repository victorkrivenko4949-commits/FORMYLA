#!/usr/bin/env python
"""Clean stage6_checkpoint.json: remove 8 failed cells from completed_cells and clear errors."""
import json
import os

CHECKPOINT_PATH = "stage6_checkpoint.json"

FAILED_CELLS = {
    "G5|L5|T004|S2",
    "G5|L5|T005|S1",
    "G5|L5|T008|S1",
    "G6|L5|T016|S1",
    "G6|L5|T018|S2",
    "G6|L5|T018|S1",
    "G6|L5|T033|S2",
    "G5|L5|T004|S0",
}

with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Before cleaning:")
print(f"  completed_cells: {len(data['completed_cells'])} cells")

# Count how many failed cells are in completed_cells
failed_in_completed = [c for c in data["completed_cells"] if c in FAILED_CELLS]
print(f"  Failed cells in completed_cells: {len(failed_in_completed)}")
for c in failed_in_completed:
    print(f"    - {c}")

# Remove failed cells from completed_cells
data["completed_cells"] = [c for c in data["completed_cells"] if c not in FAILED_CELLS]

print(f"\nAfter cleaning:")
print(f"  completed_cells: {len(data['completed_cells'])} cells")

# Clear errors
print(f"  errors before: {len(data['errors'])} entries")
data["errors"] = []
print(f"  errors after: {len(data['errors'])} entries")

# Write back
with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"\nCheckpoint saved: {os.path.getsize(CHECKPOINT_PATH)} bytes")
print("Done.")
