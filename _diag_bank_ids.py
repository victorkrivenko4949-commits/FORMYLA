#!/usr/bin/env python3
import json

with open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8') as f:
    bank = json.load(f)

r = bank[0]
print("ALL KEYS for first record:")
for k in sorted(r.keys()):
    v = r[k]
    if isinstance(v, str) and len(v) > 100:
        v = v[:80] + '...'
    print(f"  {k}: {v!r}")

print("\nID-like fields for first 10 records:")
for i in range(10):
    r = bank[i]
    oid = r.get('original_id', '?')
    id_like = {k: v for k, v in r.items() 
               if any(x in k.lower() for x in ['id', 'hash', 'internal', 'source_idx', 'original', 'task'])}
    print(f"  [{i}] {oid}: {json.dumps(id_like, ensure_ascii=False)[:200]}")
