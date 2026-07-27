#!/usr/bin/env python
"""Inspect Stage 7 checkpoint to see how far verification got."""
import json

fp = 'l4_l5_finalization/stage7_checkpoint.json'
try:
    d = json.load(open(fp, 'r', encoding='utf-8'))
    print(f"Top-level keys: {list(d.keys())}")
    for k in ['verified', 'rejected', 'conflicts']:
        val = d.get(k, {})
        if isinstance(val, dict):
            print(f"  '{k}': dict with {len(val)} keys")
            if len(val) > 0:
                sample = list(val.keys())[:3]
                print(f"    Sample keys: {sample}")
        elif isinstance(val, list):
            print(f"  '{k}': list with {len(val)} items")
        else:
            print(f"  '{k}': {type(val).__name__} = {val}")
    
    # Also check conflicts separately if present
    if 'conflicts' in d and isinstance(d['conflicts'], list) and len(d['conflicts']) > 0:
        print(f"\nFirst conflict sample:")
        print(json.dumps(d['conflicts'][0], indent=2, ensure_ascii=False)[:500])
except Exception as e:
    print(f"Error reading checkpoint: {e}")
