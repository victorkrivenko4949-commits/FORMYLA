#!/usr/bin/env python3
import json

with open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8') as f:
    bank = json.load(f)

print(f"Total tasks: {len(bank)}")

# Find class 8 L3 tasks
c8l3 = [t for t in bank if t.get('class_level') == 8 and t.get('target_level') == 'L3']
print(f"Class 8 L3 tasks: {len(c8l3)}")

# Print first one fully
if c8l3:
    print("\n=== FIRST CLASS 8 L3 TASK ===")
    print(json.dumps(c8l3[0], ensure_ascii=False, indent=2))

# Print all topics
print("\n=== ALL CLASS 8 L3 TOPICS ===")
for t in c8l3:
    print(f"  original_id={t.get('original_id','?')} | topic={t.get('topic','?')} | statement[:80]={t.get('statement','')[:80]}")

# Find max original_id among class 8
ids = [t.get('original_id', '') for t in bank if t.get('class_level') == 8]
print(f"\nClass 8 original_ids sample: {ids[:10]}")
