#!/usr/bin/env python
"""Deduplicate stage6_generated_tasks.json by task_id and statement."""
import json
from collections import Counter

path = 'stage6_generated_tasks.json'
data = json.load(open(path, 'r', encoding='utf-8'))
print(f'Before: {len(data)} tasks')

# --- Pass 1: remove by duplicate task_id ---
seen_ids = set()
deduped_by_id = []
for t in data:
    tid = t.get('task_id', '')
    if tid not in seen_ids:
        seen_ids.add(tid)
        deduped_by_id.append(t)
    else:
        print(f'  Removed duplicate task_id: {tid}')

print(f'After dedup by id: {len(deduped_by_id)} tasks')

# --- Pass 2: remove by duplicate (cell_key, statement) ---
cell_stmt = {}
deduped_final = []
for t in deduped_by_id:
    key = (t.get('cell_key', ''), t.get('statement', ''))
    if key not in cell_stmt:
        cell_stmt[key] = True
        deduped_final.append(t)
    else:
        print(f'  Removed duplicate statement in {key[0]}')

print(f'After dedup by statement: {len(deduped_final)} tasks')
print(f'Removed {len(data) - len(deduped_final)} tasks total')

# --- Verify no remaining dupes ---
ids = [t.get('task_id', '') for t in deduped_final]
dupes = {tid: cnt for tid, cnt in Counter(ids).items() if cnt > 1}
print(f'Remaining duplicate ids: {dupes}')

# --- Save ---
json.dump(deduped_final, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'Saved {len(deduped_final)} tasks to {path}')
