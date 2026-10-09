#!/usr/bin/env python3
import json

# Load bank
with open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8') as f:
    bank = json.load(f)

records = bank if isinstance(bank, list) else bank.get('tasks', bank.get('records', []))

# Show ALL keys of first 3 records
print("=== First 3 records - ALL keys ===")
for i in range(3):
    r = records[i]
    print(f"\nRecord {i}:")
    for k, v in sorted(r.items()):
        val = str(v)[:100]
        print(f"  {k}: {val}")

# Check if any bank records have IDs matching lineage format
print("\n=== Lineage task_id format check ===")
lineage_path = "l4_l5_finalization/taxonomy_reconstruction/task_lineage.jsonl"
lineage_ids = set()
with open(lineage_path, 'r', encoding='utf-8') as f:
    for line in f:
        entry = json.loads(line.strip())
        lineage_ids.add(entry["task_id"])

print(f"Lineage has {len(lineage_ids)} unique task_ids")
print(f"Sample lineage IDs: {list(lineage_ids)[:5]}")

# Check if ANY bank ID matches any lineage ID
bank_ids_oid = set()
bank_ids_tid = set()
for r in records:
    oid = r.get('original_id')
    tid = r.get('task_id')
    if oid: bank_ids_oid.add(str(oid))
    if tid: bank_ids_tid.add(str(tid))

print(f"\nBank original_id samples: {list(bank_ids_oid)[:5]}")
print(f"Bank task_id samples: {list(bank_ids_tid)[:5]}")

overlap_oid = lineage_ids & bank_ids_oid
overlap_tid = lineage_ids & bank_ids_tid
print(f"\nOverlap original_id vs lineage: {len(overlap_oid)}")
print(f"Overlap task_id vs lineage: {len(overlap_tid)}")

# Check topic field encoding
print("\n=== Topic field samples ===")
for r in records[:3]:
    topic = r.get('topic', '')
    print(f"  topic={repr(topic)}")
