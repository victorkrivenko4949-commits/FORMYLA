#!/usr/bin/env python3
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Read as binary
with open('olympiads.py', 'rb') as f:
    raw = f.read()

print(f"File size: {len(raw)} bytes")
null_count = raw.count(b'\x00')
print(f"Null bytes: {null_count}")

if null_count > 0:
    for i, b in enumerate(raw):
        if b == 0:
            start = max(0, i-10)
            end = min(len(raw), i+10)
            print(f"  Null at byte {i}: context={raw[start:end]}")
else:
    print("No null bytes found in binary read")

# Read as text
with open('olympiads.py', 'r', encoding='utf-8') as f:
    text = f.read()
print(f"Text length: {len(text)} chars")

# Try to find the variable
if 'OLYMPIADS_DB' in text:
    idx = text.index('OLYMPIADS_DB')
    print(f"OLYMPIADS_DB found at position {idx}")
    # Check the structure around it
    print(f"Context: {text[idx:idx+100]}")
else:
    print("OLYMPIADS_DB NOT FOUND!")
