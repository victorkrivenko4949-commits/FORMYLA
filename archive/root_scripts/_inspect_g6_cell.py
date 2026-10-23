#!/usr/bin/env python
"""Inspect g6|Теория чисел, делимость cell contents - only L2, exact topic match."""
import json

DB_PATH = "adaptive_data/adaptive_full_9120_fixed.json"
db = json.load(open(DB_PATH, encoding="utf-8"))

# Exact cell key: level=2, grade=6, topic="Теория чисел, делимость"
cell = [t for t in db if t.get("level") == 2 and t.get("grade") == 6 and t.get("topic") == "Теория чисел, делимость"]

print(f"L2|g6|Теория чисел, делимость: {len(cell)} tasks")
print()

for i, t in enumerate(cell):
    stmt = t.get("statement", "")
    ans = t.get("answer", "")
    print(f"--- Task {i+1} (id={t.get('id','?')}) ---")
    print(f"  statement[:300] = {repr(stmt[:300])}")
    print(f"  answer[:200]   = {repr(ans[:200])}")
    # Fingerprint for duplicate detection
    fp = stmt[:100].lower().replace(" ", "")
    print(f"  fingerprint    = {repr(fp)}")
    print()
