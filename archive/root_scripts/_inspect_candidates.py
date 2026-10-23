#!/usr/bin/env python
import json, sys

fp = 'l4_l5_finalization/stage6_candidates.json'
d = json.load(open(fp, 'r', encoding='utf-8'))

print(f"Top-level keys: {list(d.keys())}")
for k, v in d.items():
    if isinstance(v, dict):
        print(f"  '{k}': dict with {len(v)} keys")
        sub_keys = list(v.keys())[:3]
        print(f"    Sample keys: {sub_keys}")
        if len(v) > 0:
            first_val = v[sub_keys[0]]
            if isinstance(first_val, dict):
                print(f"    Entry fields: {list(first_val.keys())}")
    elif isinstance(v, list):
        print(f"  '{k}': list of {len(v)} items")
    elif isinstance(v, str):
        print(f"  '{k}': str (len={len(v)})")
    else:
        print(f"  '{k}': {type(v).__name__} = {v}")
