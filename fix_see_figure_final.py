#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Final fix for см. рисунок"""

with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()

before = content.count('(см. рисунок)') + content.count('см. рисунок')
print(f'Before: {before} instances')

# Remove all variants
content = content.replace('(см. рисунок)', '')
content = content.replace('см. рисунок', '')
content = content.replace('(см.\nрисунок)', '')
content = content.replace('см.\nрисунок', '')

# Clean double spaces
while '  ' in content:
    content = content.replace('  ', ' ')

with open('olympiads.py', 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
with open('olympiads.py', 'r', encoding='utf-8') as f:
    new_content = f.read()

after = new_content.count('(см. рисунок)') + new_content.count('см. рисунок')
print(f'After: {after} instances')
print(f'Removed: {before - after}')
