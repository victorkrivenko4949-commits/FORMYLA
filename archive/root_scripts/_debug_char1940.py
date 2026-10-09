#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find what character is at position 1940 in the JSON."""
import json

with open('_last_response_11_v2.txt', 'r', encoding='utf-8') as f:
    raw = f.read()

# Strip markdown fences
text = raw
if '```json' in text:
    text = text.split('```json', 1)[1]
    if '```' in text:
        text = text.split('```', 1)[0]
text = text.strip()

# Show what's at position 1940
pos = 1940
print(f'Char at pos {pos}: {repr(text[pos])} (ord={ord(text[pos])})')
print(f'Context [{pos-50}:{pos+50}]:')
print(repr(text[pos-50:pos+50]))

# Also check for unescaped quotes and invalid backslash sequences
print(f'\nSearching for issues...')

# Find all backslash positions
for i in range(len(text)):
    c = text[i]
    if c == '\\':
        # Check if it's a valid JSON escape
        if i+1 < len(text):
            nextc = text[i+1]
            if nextc not in '"\\/bfnrtu':
                print(f'  INVALID escape at pos {i}: \\{nextc}')
                print(f'  Context: {repr(text[max(0,i-30):i+30])}')
    elif c == '"':
        # Check if it's inside a JSON string by counting backslashes before it
        # This is complex, skip for now
        pass

# Try to find unescaped quotes inside strings
# Simple approach: try to find where JSON breaks
# Let's just look at the first error more carefully
print(f'\nDetailed error analysis:')
try:
    json.loads(text)
except json.JSONDecodeError as e:
    print(f'JSON error at pos {e.pos}: {e.msg}')
    # Show detailed context
    start = max(0, e.pos - 100)
    end = min(len(text), e.pos + 100)
    context = text[start:end]
    print(f'Context ({start}-{end}):')
    for i, ch in enumerate(context):
        abs_pos = start + i
        if abs_pos == e.pos:
            print(f'  >>>{repr(ch)}<<< at position {abs_pos} (ord={ord(ch)})')
        elif ch in '\\"':
            print(f'  {repr(ch)} at position {abs_pos}')
