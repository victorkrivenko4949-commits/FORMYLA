#!/usr/bin/env python
"""Test the updated sanitize/parse functions on the previously-failed raw responses."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _stage6_targeted_generation import (
    sanitize_json_string,
    parse_json_response,
    _extract_tasks_known_structure,
)

FAILED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stage6_failed_responses")

# The 8 failed cells and their raw file names
failed_cells = {
    "G5|L5|T004|S2": "raw_G5_L5_T004_S2.txt",
    "G5|L5|T005|S1": "raw_G5_L5_T005_S1.txt",
    "G5|L5|T008|S1": "raw_G5_L5_T008_S1.txt",
    "G6|L5|T016|S1": "raw_G6_L5_T016_S1.txt",
    "G6|L5|T018|S2": "raw_G6_L5_T018_S2.txt",
    "G6|L5|T033|S2": "raw_G6_L5_T033_S2.txt",
    "G5|L5|T004|S0": "raw_G5_L5_T004_S0.txt",
    "G6|L5|T018|S1": "raw_G6_L5_T018_S1.txt",
}

print("=" * 80)
print("TEST: Fix for unescaped quotes in JSON strings")
print("=" * 80)

passed = 0
failed = 0
total = len(failed_cells)

for cell_key, raw_file in failed_cells.items():
    raw_path = os.path.join(FAILED_DIR, raw_file)
    if not os.path.exists(raw_path):
        print(f"\n  [{cell_key}] SKIP — file not found: {raw_file}")
        continue
    
    with open(raw_path, "r", encoding="utf-8") as f:
        text = f.read()
    
    print(f"\n  [{cell_key}] ({raw_file}) — {len(text)} bytes")
    
    # Test 1: Direct parse (should fail for all)
    import json
    try:
        result = json.loads(text)
        print(f"    Direct JSON.parse: OK ({len(result.get('tasks', result)) if isinstance(result, dict) else len(result)} entries)")
    except json.JSONDecodeError as e:
        print(f"    Direct JSON.parse: FAILED ({str(e)[:80]})")
    
    # Test 2: Sanitized parse
    sanitized = sanitize_json_string(text)
    try:
        result = json.loads(sanitized)
        print(f"    Sanitized parse:    OK ({len(result.get('tasks', result)) if isinstance(result, dict) else len(result)} entries)")
    except json.JSONDecodeError as e:
        print(f"    Sanitized parse:    FAILED ({str(e)[:80]})")
    
    # Test 3: Strategy 6 (known structure)
    result = _extract_tasks_known_structure(text)
    if result and "tasks" in result:
        print(f"    Strategy 6 (raw):   OK ({len(result['tasks'])} tasks extracted)")
    else:
        print(f"    Strategy 6 (raw):   FAILED (no tasks found)")
    
    result2 = _extract_tasks_known_structure(sanitized)
    if result2 and "tasks" in result2:
        print(f"    Strategy 6 (san.):  OK ({len(result2['tasks'])} tasks extracted)")
    else:
        print(f"    Strategy 6 (san.):  FAILED (no tasks found)")
    
    # Test 4: Full parse_json_response
    try:
        result3 = parse_json_response(text, save_on_failure=False)
        if isinstance(result3, dict) and "tasks" in result3:
            tasks_list = result3["tasks"]
        elif isinstance(result3, list):
            tasks_list = result3
        else:
            tasks_list = []
        print(f"    parse_json_response: OK ({len(tasks_list)} tasks)")
        passed += 1
    except (ValueError, json.JSONDecodeError) as e:
        print(f"    parse_json_response: FAILED ({str(e)[:120]})")
        failed += 1

print(f"\n{'=' * 80}")
print(f"RESULT: {passed}/{total} passed, {failed}/{total} failed")
print(f"{'=' * 80}")

# Also test the known failed_unknown files
print(f"\n{'=' * 80}")
print("Testing failed_unknown files too...")
print(f"{'=' * 80}")

unknown_passed = 0
unknown_total = 0
for fname in sorted(os.listdir(FAILED_DIR)):
    if fname.startswith("failed_unknown_") and fname.endswith(".txt"):
        path = os.path.join(FAILED_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        try:
            result = parse_json_response(text, save_on_failure=False)
            if isinstance(result, dict) and "tasks" in result:
                cnt = len(result["tasks"])
            elif isinstance(result, list):
                cnt = len(result)
            else:
                cnt = 0
            print(f"  {fname}: OK ({cnt} tasks)")
            unknown_passed += 1
        except (ValueError, json.JSONDecodeError) as e:
            print(f"  {fname}: FAILED ({str(e)[:80]})")
        unknown_total += 1

print(f"\nUnknown files: {unknown_passed}/{unknown_total} passed")
