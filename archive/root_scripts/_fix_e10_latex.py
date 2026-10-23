#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find and fix the LaTeX error in E10. Двойной счёт article."""

import json
import re

with open('secrets_dump.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for i, entry in enumerate(data):
    title = entry.get('title', '')
    if 'E10' in title and 'Двойной' in title:
        print(f"Entry index: {i}")
        print(f"Title: {title}")
        content = entry.get('content', '')
        
        # Find all # positions in content
        hash_positions = []
        pos = 0
        while True:
            pos = content.find('#', pos)
            if pos == -1:
                break
            hash_positions.append(pos)
            pos += 1
        
        print(f"\nTotal '#' occurrences: {len(hash_positions)}")
        for hp in hash_positions:
            ctx = content[hp:min(hp+120, len(content))]
            print(f"  pos {hp}: {repr(ctx)}")
        
        # Find разноцветных
        idx = content.find('разноцветных')
        if idx >= 0:
            print(f"\n\n'разноцветных' at position {idx}")
            print(repr(content[max(0,idx-80):idx+200]))
        
        # Find квадратов 2×2
        idx2 = content.find('квадратов 2×2')
        if idx2 >= 0:
            print(f"\n\n'квадратов 2×2' at position {idx2}")
            print(repr(content[max(0,idx2-80):idx2+200]))
        else:
            idx2b = content.find('квадратов')
            if idx2b >= 0:
                print(f"\n\n'квадратов' at position {idx2b}")
                print(repr(content[max(0,idx2b-80):idx2b+200]))
