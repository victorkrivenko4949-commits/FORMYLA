#!/usr/bin/env python
"""Quick test for sanitize_json_string on real raw responses."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the sanitize function directly
from l4_l5_completion_work._stage6_targeted_generation import sanitize_json_string, _VALID_JSON_ESCAPES

print(f"_VALID_JSON_ESCAPES = {_VALID_JSON_ESCAPES}")
print()

# Read a raw response
raw_path = os.path.join(os.path.dirname(__file__), "stage6_failed_responses", "raw_G11_L5_T001_S1.txt")
with open(raw_path, "r", encoding="utf-8") as f:
    raw = f.read()

print(f"Raw length: {len(raw)}")
print(f"Raw first 200 repr: {repr(raw[:200])}")
print()

# Check if \( is present with single backslash
bs_paren = "\\(" in raw
print(f"Contains \\( (single backslash): {bs_paren}")
# Check with find
idx = raw.find("\\(")
if idx >= 0:
    print(f"  Found at index {idx}, context: {repr(raw[max(0,idx-5):idx+15])}")

print()

sanitized = sanitize_json_string(raw)
print(f"Sanitized length: {len(sanitized)}")
print(f"Sanitized first 300 repr: {repr(sanitized[:300])}")
print()

# Try to parse
try:
    result = json.loads(sanitized)
    print("=== PARSE SUCCESS ===")
    print(f"Number of tasks: {len(result.get('tasks', []))}")
    t0 = result["tasks"][0]
    print(f"First task statement (first 100): {t0['statement'][:100]}")
except json.JSONDecodeError as e:
    print(f"PARSE FAILED: {e}")
    pos = e.pos
    context = sanitized[max(0,pos-80):pos+80]
    print(f"Context around error: {repr(context)}")
    
    # Find the problematic character
    for i in range(max(0, pos-5), min(len(sanitized), pos+5)):
        ch = sanitized[i]
        if ord(ch) < 0x20 or ch in '\\':
            print(f"  Char at {i}: {repr(ch)} (ord={ord(ch)})")
