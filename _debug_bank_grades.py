#!/usr/bin/env python
import json
from collections import Counter

with open('curated_bank_L1_L5_fixed.json', 'r', encoding='utf-8') as f:
    bank = json.load(f)

with open('_debug_bank_grades.txt', 'w', encoding='utf-8') as out:
    for i, t in enumerate(bank[:20]):
        out.write(f"[{i}] grade={repr(t.get('grade'))} level={repr(t.get('level'))}\n")
    
    for i, t in enumerate(bank[:20]):
        tl = t.get('target_level','?')
        out.write(f"[{i}] target_level={repr(tl)}\n")
    
    gl = Counter()
    for t in bank:
        gl[f"{t.get('grade','?')}|{t.get('level','?')}"] += 1
    
    out.write("\n=== Grade|Level combos ===\n")
    for k, v in sorted(gl.items()):
        out.write(f"  {k}: {v}\n")
    
    tl = Counter()
    for t in bank:
        tl[t.get('target_level','?')] += 1
    
    out.write("\n=== target_level ===\n")
    for k, v in sorted(tl.items()):
        out.write(f"  target_level={repr(k)}: {v}\n")
    
    # Also show first 3 bank task keys
    out.write(f"\n=== Bank[0] keys ===\n")
    for k in bank[0].keys():
        out.write(f"  {k}: {repr(bank[0][k])[:100]}\n")
    
    # Check class_level field
    cl = Counter()
    for t in bank:
        cl[t.get('class_level','?')] += 1
    out.write("\n=== class_level ===\n")
    for k, v in sorted(cl.items()):
        out.write(f"  class_level={repr(k)}: {v}\n")

print("Written to _debug_bank_grades.txt")
