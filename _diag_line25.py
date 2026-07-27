#!/usr/bin/env python3
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

with open('olympiads.py', 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

for i in range(20, 30):
    if i < len(lines):
        line = lines[i]
        print(f'Line {i+1} (len={len(line)}): {repr(line[:200])}')
