#!/usr/bin/env python3
"""Diagnostic for idx 1042 current state."""
import sys, json
sys.path.insert(0, '.')
import olympiads

entry = olympiads.OLYMPIADS_DB[1042]
print(f"idx 1042: id={entry.get('id')}, grade={entry.get('grade')}, problems={len(entry.get('problems',[]))}")
for p in entry.get('problems', []):
    txt = (p.get('text') or '')[:150]
    print(f"  num={p.get('num')} day={p.get('day')}: {txt}")
