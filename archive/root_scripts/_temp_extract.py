#!/usr/bin/env python3
"""Extract vsosh 2020 regional entries for editing."""
import sys, json
sys.path.insert(0, 'C:/Users/Victor/Desktop/Новая папка (2)')
import olympiads

db = olympiads.OLYMPIADS_DB

# Find vsosh 2020 regional entries
targets = []
for idx, o in enumerate(db):
    if isinstance(o, dict) and o.get('olympiad') == 'vsosh' and o.get('year') == 2020 and o.get('round') == 'regional':
        targets.append((idx, o))
        print(f"Index={idx} id={o.get('id')} grade={o['grade']} probs={len(o['problems'])}")
        for p in o['problems']:
            print(f"  num={p['num']} text[:60]={p['text'][:60]}")

print(f"\nFound {len(targets)} vsosh 2020 regional entries")
print(f"Indices to modify: {[t[0] for t in targets]}")
