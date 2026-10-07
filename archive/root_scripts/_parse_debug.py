#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Debug parse: read _last_response_11_v2.txt and extract JSON."""
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

print(f'JSON text length: {len(text)}')
print(f'First 80: {text[:80]}')
print(f'Last 80: {text[-80:]}')

try:
    data = json.loads(text)
    print(f'SUCCESS! Parsed {len(data)} items')
    for p in data:
        print(f'  num={p.get("num")}: text={p.get("text","")[:60]}...')
except json.JSONDecodeError as e:
    print(f'ERROR: {e}')
    pos = e.pos
    print(f'Context around position {pos}:')
    start = max(0, pos - 200)
    end = min(len(text), pos + 200)
    snippet = text[start:end]
    # Show with visible whitespace markers
    print(repr(snippet))
