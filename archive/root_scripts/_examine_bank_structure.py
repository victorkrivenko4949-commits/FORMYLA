#!/usr/bin/env python3
"""Examine curated bank structure - find class 8 L3 tasks."""
import json
import sys

def main():
    bank_path = "curated_bank_L1_L5_fixed.json"
    with open(bank_path, "r", encoding="utf-8") as f:
        bank = json.load(f)
    
    print(f"Total tasks in bank: {len(bank)}", flush=True)
    
    if len(bank) == 0:
        print("EMPTY BANK!", flush=True)
        return
    
    # Print keys of first task
    first = bank[0]
    print(f"\nFirst task keys: {list(first.keys())}", flush=True)
    print(f"First task 'id': {first.get('id', 'N/A')}", flush=True)
    
    # Check field names for class/grade and level
    for field in ['class_level', 'class', 'grade', 'grade_level', 'target_level', 'level']:
        if field in first:
            print(f"First task {field}: {first[field]}", flush=True)
    
    # Find class 8 tasks
    class8_tasks = []
    for t in bank:
        cl = t.get('class_level') or t.get('class') or t.get('grade') or t.get('grade_level', 0)
        try:
            cl_int = int(cl) if cl is not None else 0
        except (ValueError, TypeError):
            cl_int = 0
        if cl_int == 8:
            class8_tasks.append(t)
    
    print(f"\nClass 8 total: {len(class8_tasks)}", flush=True)
    
    # Count by target_level
    from collections import Counter
    levels = Counter()
    for t in class8_tasks:
        tl = t.get('target_level') or t.get('level') or 'N/A'
        levels[tl] += 1
    
    for lvl, cnt in sorted(levels.items()):
        print(f"  Class 8, {lvl}: {cnt}", flush=True)
    
    # Show class 8 L3 tasks
    l3_tasks = [t for t in class8_tasks if (t.get('target_level') or t.get('level')) == 'L3']
    print(f"\nClass 8 L3 tasks: {len(l3_tasks)}", flush=True)
    for i, t in enumerate(l3_tasks[:5]):
        tid = t.get('id', 'N/A')
        topic = t.get('topic', t.get('subtopic', 'N/A'))
        text_preview = (t.get('text', t.get('condition', '')) or '')[:120]
        print(f"\n  [{i+1}] ID: {tid}", flush=True)
        print(f"       Topic: {json.dumps(topic, ensure_ascii=False)}", flush=True)
        print(f"       Text: {text_preview}...", flush=True)

if __name__ == '__main__':
    main()
