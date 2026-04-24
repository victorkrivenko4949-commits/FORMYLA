# -*- coding: utf-8 -*-
"""Verify the test output from import_official_solutions.py"""
import sys
sys.path.insert(0, '.')

# Load test output file directly
import importlib.util
spec = importlib.util.spec_from_file_location("test_out", "olympiads_test_output.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
db = mod.OLYMPIADS_DB

combo = db[0]
print("=" * 70)
print(f"Combo: {combo.get('source_name')}")
print(f"Source URL: {combo.get('source_url')}")
print(f"Solutions imported: {combo.get('solutions_imported')}")
print()

for p in combo['problems']:
    print(f"--- Problem {p['num']} ---")
    print(f"  Keys: {list(p.keys())}")
    print(f"  Verified: {p.get('solution_verified')}")
    print(f"  Confidence: {p.get('solution_confidence')}")
    print(f"  Needs review: {p.get('needs_manual_review')}")
    sol = p.get('official_solution', '')
    if sol:
        print(f"  Official solution (first 400 chars):")
        print(f"  {sol[:400]}")
    else:
        print(f"  No official solution")
    print()
