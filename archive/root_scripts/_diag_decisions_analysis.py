#!/usr/bin/env python3
"""Analyze decisions.jsonl for class 8 tasks to understand the shortage."""
import json
from collections import Counter

RUN_DIR = r"../../Downloads/FORMYLA_CONDITION_COURT/runs/selection_1080_20260718_175442"

# Load decisions.jsonl
decisions = []
with open(f"{RUN_DIR}/decisions.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        if d.get("class_level") == 8:
            decisions.append(d)

print(f"Class 8 total in input: {len(decisions)}")
print()

# By decision
dec_counts = Counter(d.get("decision") for d in decisions)
print(f"By decision: {dict(sorted(dec_counts.items()))}")
print()

# APPROVE by target_level
tl_counts = Counter()
for d in decisions:
    if d.get("decision") == "APPROVE":
        tl = d.get("target_level", "?")
        tl_counts[tl] += 1
print(f"APPROVE by target_level: {dict(sorted(tl_counts.items()))}")
print()

# L3 tasks - show some details
l3_tasks = [d for d in decisions if d.get("target_level") == "L3"]
print(f"Total class 8 with target_level=L3: {len(l3_tasks)}")
print(f"  APPROVE L3: {len([d for d in l3_tasks if d.get('decision') == 'APPROVE'])}")
print(f"  RECHECK L3: {len([d for d in l3_tasks if d.get('decision') == 'RECHECK'])}")
print(f"  QUARANTINE L3: {len([d for d in l3_tasks if d.get('decision') == 'QUARANTINE'])}")
print(f"  REJECT L3: {len([d for d in l3_tasks if d.get('decision') == 'REJECT'])}")
print()

# What decisions do non-L3 class 8 tasks have?
non_l3 = [d for d in decisions if d.get("target_level") != "L3"]
print(f"Class 8 non-L3 tasks: {len(non_l3)}")
non_l3_dec = Counter(d.get("decision") for d in non_l3)
print(f"  By decision: {dict(sorted(non_l3_dec.items()))}")
non_l3_tl = Counter(d.get("target_level") for d in non_l3 if d.get("decision") == "APPROVE")
print(f"  APPROVE non-L3 by target_level: {dict(sorted(non_l3_tl.items()))}")
print()

# RECHECK tasks - full details
recheck = [d for d in decisions if d.get("decision") == "RECHECK"]
print(f"RECHECK tasks: {len(recheck)}")
for r in recheck:
    print(f"  ID={r['original_id']} class={r.get('class_level')} target={r.get('target_level')} diff={r.get('original_difficulty')}")
    print(f"    rationale: {r.get('rationale', '')[:200]}")
print()

# QUARANTINE tasks
quarantine = [d for d in decisions if d.get("decision") == "QUARANTINE"]
print(f"QUARANTINE tasks: {len(quarantine)}")
for q in quarantine:
    print(f"  ID={q['original_id']} class={q.get('class_level')} target={q.get('target_level')}")
print()

# Summary
print("=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"Class 8 input tasks: {len(decisions)}")
print(f"APPROVE for cell (8,L3): {len([d for d in l3_tasks if d.get('decision') == 'APPROVE'])}")
print(f"Shortage: 21 - {len([d for d in l3_tasks if d.get('decision') == 'APPROVE'])} = {21 - len([d for d in l3_tasks if d.get('decision') == 'APPROVE'])}")

# Check if any APPROVE_RESERVE exists
reserve_count = len([d for d in decisions if d.get("decision") == "APPROVE_RESERVE"])
print(f"APPROVE_RESERVE class 8: {reserve_count}")
