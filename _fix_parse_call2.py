#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnose and fix the Call 2 JSON parsing issue.
Load the raw response file, try various parsing strategies, and identify the issue.
"""
import json
import os

os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

def fix_json_escapes(text):
    """Fix invalid backslash escapes in JSON string content."""
    VALID_ESCAPES = set('"\\/bfnrtu')
    result = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\' and i + 1 < len(text):
            nextc = text[i + 1]
            if nextc in VALID_ESCAPES:
                result.append(c)
                result.append(nextc)
                i += 2
            else:
                result.append('\\\\')
                result.append(nextc)
                i += 2
        else:
            result.append(c)
            i += 1
    return ''.join(result)


# Load raw response
with open('_last_response_11_v4_call2.txt', 'r', encoding='utf-8') as f:
    raw = f.read()

print(f"Raw response: {len(raw)} chars")
print(f"Has [ : {'[' in raw}")
print(f"Has ] : {']' in raw}")
print(f"Ends with ]: {raw.rstrip().endswith(']')}")
print()

# Strategy 1: Try direct parse (no fix)
print("=== Strategy 1: Direct parse (no fix)===")
try:
    data = json.loads(raw)
    print(f"SUCCESS! Got {len(data) if isinstance(data, list) else 'dict'} items")
    for p in data if isinstance(data, list) else [data]:
        print(f"  Problem {p.get('num')}: text={p.get('text','')[:80]}")
except json.JSONDecodeError as e:
    print(f"FAILED: {e}")
    print(f"  Position: {e.pos}")
    # Show context around error
    start = max(0, e.pos - 100)
    end = min(len(raw), e.pos + 100)
    context = raw[start:end]
    print(f"  Context: {repr(context)}")
print()

# Strategy 2: Try with fix_json_escapes
print("=== Strategy 2: With fix_json_escapes ===")
fixed = fix_json_escapes(raw)
try:
    data = json.loads(fixed)
    print(f"SUCCESS! Got {len(data) if isinstance(data, list) else 'dict'} items")
    for p in data if isinstance(data, list) else [data]:
        print(f"  Problem {p.get('num')}: text={p.get('text','')[:80]}")
except json.JSONDecodeError as e:
    print(f"FAILED: {e}")
    print(f"  Position: {e.pos}")
    start = max(0, e.pos - 100)
    end = min(len(fixed), e.pos + 100)
    context = fixed[start:end]
    print(f"  Context: {repr(context)}")
print()

# Strategy 3: Try parsing only the raw file (already written by script)
# The raw file was written BEFORE fix_json_escapes was applied
# So the raw file should have single-backslash LaTeX
# Let's check for any problematic chars
print("=== Strategy 3: Find problematic chars ===")
problem_chars = []
for i, c in enumerate(raw):
    if ord(c) < 32 and c not in '\n\r\t':
        problem_chars.append((i, ord(c), repr(c)))
if problem_chars:
    print(f"Found {len(problem_chars)} control chars:")
    for pos, code, char in problem_chars[:20]:
        print(f"  Position {pos}: code {code} = {char}")
else:
    print("No control characters found")
print()

# Strategy 4: Check for unescaped double quotes in strings
print("=== Strategy 4: Check for LaTeX-style unescaped quotes ===")
# Sometimes DeepSeek puts literal " inside JSON string values
# Find all " characters that are not at the start/end of a JSON key/value
count_before_after = 0
lines = raw.split('\n')
for i, line in enumerate(lines):
    stripped = line.strip()
    # Check if line is inside a JSON string value (between ":" and "," or "}")
    if ':' in stripped and not stripped.startswith('[') and not stripped.startswith(']') and not stripped.startswith('{') and not stripped.startswith('}'):
        colon_pos = stripped.index(':')
        value_part = stripped[colon_pos+1:].strip()
        # If value starts with " (string), check for unescaped quotes inside
        if value_part.startswith('"'):
            # Find closing quote
            quote_end = value_part.rfind('"')
            if quote_end > 0:
                inner = value_part[1:quote_end]
                # Count unescaped quotes
                j = 0
                unescaped = []
                while j < len(inner):
                    if inner[j] == '"' and (j == 0 or inner[j-1] != '\\'):
                        unescaped.append(j)
                    j += 1
                if unescaped:
                    print(f"  Line {i+1}: {len(unescaped)} unescaped quotes in string value")
                    for pos in unescaped[:5]:
                        ctx = inner[max(0,pos-20):pos+20]
                        print(f"    pos {pos}: ...{repr(ctx)}...")
print()

# Strategy 5: Extract between [ and ] and try
print("=== Strategy 5: Extract between [ ] ===")
start = raw.find('[')
end = raw.rfind(']')
if start >= 0 and end > start:
    snippet = raw[start:end+1]
    print(f"Extracted snippet: {len(snippet)} chars (from {start} to {end})")
    try:
        data = json.loads(snippet)
        print(f"SUCCESS! Got {len(data)} items")
        for p in data:
            print(f"  Problem {p.get('num')}: text={p.get('text','')[:80]}")
    except json.JSONDecodeError as e:
        print(f"FAILED: {e}")
        print(f"  Position: {e.pos}")
        start_ctx = max(0, e.pos - 100)
        end_ctx = min(len(snippet), e.pos + 100)
        context = snippet[start_ctx:end_ctx]
        print(f"  Context: {repr(context)}")
print()

# Strategy 6: Try fix_json_escapes on extracted snippet
print("=== Strategy 6: Extract + fix_json_escapes ===")
if start >= 0 and end > start:
    snippet = raw[start:end+1]
    fixed_snippet = fix_json_escapes(snippet)
    try:
        data = json.loads(fixed_snippet)
        print(f"SUCCESS! Got {len(data)} items")
        for p in data:
            print(f"  Problem {p.get('num')}: text={p.get('text','')[:80]}")
    except json.JSONDecodeError as e:
        print(f"FAILED: {e}")
        print(f"  Position: {e.pos}")
        start_ctx = max(0, e.pos - 100)
        end_ctx = min(len(fixed_snippet), e.pos + 100)
        context = fixed_snippet[start_ctx:end_ctx]
        print(f"  Context: {repr(context)}")
