#!/usr/bin/env python
"""Targeted script to fill remaining L3 tasks for a specific cell key."""
import json, sys
from _fill_l3_holes import (
    DeepSeekClient, generate_cell_tasks, merge_into_db,
    get_l3_cells_with_holes,
    DB_PATH, OUTPUT_FILE, NEW_TASKS_FILE, TARGET
)

TARGET_CELL_KEY = "L3|9|Алгебра. Системы иррациональных уравнений с параметром"

with open(DB_PATH, 'r', encoding='utf-8') as f:
    db = json.load(f)

cells = get_l3_cells_with_holes(db)
cell_info = None
for c in cells:
    if c['cell_key'] == TARGET_CELL_KEY:
        cell_info = c
        break

if not cell_info:
    print(f"Cell not found: {TARGET_CELL_KEY}")
    print("Available L3 cells with holes:")
    for c in cells:
        print(f"  {c['cell_key']} — {c['count']}/{TARGET} (need {c['needed']})")
    sys.exit(1)

need = cell_info['needed']
print(f"Target: {cell_info['cell_key']} — {cell_info['count']}/{TARGET} (need {need})")

if need <= 0:
    print("Cell already full!")
    sys.exit(0)

client = DeepSeekClient()
new_tasks = generate_cell_tasks(client, cell_info)

if new_tasks:
    db = merge_into_db(db, new_tasks)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    with open(NEW_TASKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_tasks, f, ensure_ascii=False, indent=2)
    print(f"\n✓ Generated {len(new_tasks)} tasks. Merged into {OUTPUT_FILE}. Total: {len(db)} tasks.")
else:
    print("No tasks generated.")
