# -*- coding: utf-8 -*-
"""Fix foreign hex colors in templates and verify."""
import re
import os

ALLOWED = {'#070C18', '#0E1830', '#121F3C', '#1C2B4F', '#E6EBF7', '#8C9ABC', '#4C7DFF', '#6B95FF', '#3ECF8E', '#E5AC3A', '#E86A62'}

# Color replacement map
REPLACE = {
    '#0B0D12': '#070C18', '#10131A': '#0E1830', '#161A23': '#121F3C',
    '#3B82F6': '#4C7DFF', '#2563EB': '#6B95FF', '#E2E8F0': '#E6EBF7',
    '#94A3B8': '#8C9ABC', '#EF4444': '#E86A62', '#22C55E': '#3ECF8E',
    '#C8D6E5': '#E6EBF7', '#CBD5E1': '#E6EBF7', '#FCA5A5': '#E86A62',
    '#E5E7EB': '#E6EBF7', '#8B5CF6': '#6B95FF', '#2BCB6A': '#3ECF8E',
    '#38EF7D': '#3ECF8E', '#F59E0B': '#E5AC3A', '#A5B4FC': '#8C9ABC',
    '#6366F1': '#4C7DFF', '#0B0F1A': '#070C18',
}

templates = [
    'templates/figures.html',
    'templates/prep/probe.html',
]

for t in templates:
    if not os.path.exists(t):
        continue
    with open(t, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Apply replacements (case-insensitive by uppercasing both)
    for old, new in REPLACE.items():
        content = content.replace(old, new)
        content = content.replace(old.lower(), new.lower())
    
    # Remove #FFFFFF except in rgba()
    content = re.sub(r'(?<!rgba\()#FFFFFF(?![\da-fA-F])', '#E6EBF7', content, flags=re.IGNORECASE)
    # Remove standalone #FFF
    content = re.sub(r'(?<!rgba\()#FFF\b(?![\da-fA-F])', '#E6EBF7', content, flags=re.IGNORECASE)
    
    with open(t, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Verify
    with open(t, 'r', encoding='utf-8') as f:
        v = f.read()
    hexes = set(m.upper() for m in re.findall(r'#[0-9A-Fa-f]{6}', v))
    foreign = hexes - ALLOWED
    print(t, 'OK' if not foreign else 'STILL_FOREIGN: ' + str(foreign))
