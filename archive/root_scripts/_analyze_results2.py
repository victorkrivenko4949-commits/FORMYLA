#!/usr/bin/env python
"""Deep-dive into audit results structure."""
import json

with open("audit_675_full_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print("Top-level keys:", list(data.keys()))
print()

# Check summary
summary = data.get("summary", {})
print("Summary:", json.dumps(summary, ensure_ascii=False, indent=2)[:2000])
print()

# Check results structure
results = data.get("results", [])
print(f"Results list length: {len(results)}")
if len(results) > 0:
    r0 = results[0]
    print(f"First result type: {type(r0).__name__}")
    if isinstance(r0, dict):
        print(f"First result keys: {list(r0.keys())}")
        # Show a compact version
        print(f"First result (compact): {json.dumps(r0, ensure_ascii=False)[:1000]}")
    
    # Count by overall verdict
    verdicts = {}
    for r in results:
        if isinstance(r, dict):
            v = r.get("overall", r.get("verdict", "N/A"))
            verdicts[v] = verdicts.get(v, 0) + 1
    
    print(f"\nVerdict counts: {json.dumps(verdicts, ensure_ascii=False)}")
    
    # Show mismatches structure
    print(f"\nLevel mismatches count: {len(data.get('level_mismatches', []))}")
    if data.get("level_mismatches"):
        print(f"First level mismatch: {json.dumps(data['level_mismatches'][0], ensure_ascii=False)[:500]}")
    
    print(f"Class mismatches count: {len(data.get('class_mismatches', []))}")
    print(f"Topic mismatches count: {len(data.get('topic_mismatches', []))}")
    print(f"Condition issues count: {len(data.get('condition_issues', []))}")
