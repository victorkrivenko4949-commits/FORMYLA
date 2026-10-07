#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnose what the response looks like after escape fixing."""
import json
import os
os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

VALID_ESCAPES = set('"\\/bfnrtu')

def fix_json_escapes(text):
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

with open('_last_response_11_v2.txt', 'r', encoding='utf-8') as f:
    raw = f.read()

# Strip markdown fences
text = raw
if '```json' in text:
    text = text.split('```json', 1)[1]
    if '```' in text:
        text = text.split('```', 1)[0]
elif '```' in text:
    text = text.split('```', 1)[1]
    if '```' in text:
        text = text.split('```', 1)[0]
text = text.strip()

print(f"After fence strip: {len(text)} chars")
print(f"Starts with: {repr(text[:100])}")
print(f"Ends with: {repr(text[-100:])}")

# Check for common patterns
print(f"\nHas '\\\\[' : {'\\\\[' in text}")
print(f"Has '\\\\]' : {'\\\\]' in text}")
print(f"Has '[' char : {'[' in text}")
print(f"Has ']' char : {']' in text}")

# Count brackets
open_brackets = text.count('[')
close_brackets = text.count(']')
print(f"\nBrackets: {open_brackets} open, {close_brackets} close")

# First character
print(f"\nFirst char: {repr(text[0])}")
print(f"Last char: {repr(text[-1])}")

# Try fix
fixed = fix_json_escapes(text)
print(f"\nAfter fix: {len(fixed)} chars")

# Check position of first [
first_open = text.find('[')
print(f"First '[' at position {first_open}")
print(f"Context: {repr(text[first_open:first_open+200])}")

# Check position of first ]
first_close = text.find(']')
print(f"\nFirst ']' at position {first_close}")
print(f"Context: {repr(text[first_close:first_close+200])}")

# Count bracket depth
depth = 0
depths = []
for i in range(first_open, len(text)):
    if text[i] == '[':
        depth += 1
    elif text[i] == ']':
        depth -= 1
    depths.append((i, depth, text[i]))
    if depth == 0:
        print(f"\nDepth reaches 0 at position {i}")
        print(f"Context: {repr(text[i:i+200])}")
        break

# Try json.loads on fixed
print("\n--- Trying json.loads on fixed text ---")
try:
    data = json.loads(fixed)
    print(f"SUCCESS! Type: {type(data).__name__}")
    if isinstance(data, list):
        print(f"Items: {len(data)}")
except json.JSONDecodeError as e:
    print(f"FAILED: {e}")
    pos = e.pos
    print(f"Position {pos}: {repr(fixed[max(0,pos-50):pos+50])}")

# Maybe the response isn't a pure JSON array - let's check
print("\n--- Checking what's before '[' ---")
print(repr(text[:first_open]))
