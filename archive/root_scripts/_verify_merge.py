#!/usr/bin/env python3
"""Verify that solutions were merged into olympiads.py"""
import sys
import os

# Add current dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Load olympiads.py by importing it as a module
import importlib.util
spec = importlib.util.spec_from_file_location("olympiads_mod", "olympiads.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

db = mod.OLYMPIADS_DB
total_problems = 0
generated = 0
empty_solution = 0

for o in db:
    for p in o.get('problems', []):
        total_problems += 1
        if p.get('solution_status') == 'generated':
            generated += 1
            if p.get('solution'):
                empty_solution += 0
            else:
                empty_solution += 1

print(f"Total olympiads: {len(db)}")
print(f"Total problems: {total_problems}")
print(f"Problems with solution_status='generated': {generated}")
print(f"Problems with generated status but empty solution: {empty_solution}")

# Show a few examples
shown = 0
for o in db:
    for p in o.get('problems', []):
        if p.get('solution_status') == 'generated' and p.get('solution'):
            sol_preview = p['solution'][:120] if len(p['solution']) > 120 else p['solution']
            print(f"\n  [{o.get('olympiad','?')} | {o.get('year','?')} | g{o.get('grade','?')}] #{p.get('num','?')}")
            print(f"  Solution preview: {sol_preview}...")
            shown += 1
            if shown >= 3:
                break
    if shown >= 3:
        break

print(f"\n{'='*50}")
print(f"VERIFICATION: {'PASSED' if generated == 60 else 'FAILED'}")
print(f"Expected 60 generated solutions, found {generated}")
