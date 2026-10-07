# -*- coding: utf-8 -*-
"""Fix foreign hex colors and emojis in all templates."""
import re
import os

ALLOWED = {'#070C18', '#0E1830', '#121F3C', '#1C2B4F', '#E6EBF7', '#8C9ABC', '#4C7DFF', '#6B95FF', '#3ECF8E', '#E5AC3A', '#E86A62'}

REPLACE = {
    '#0B0D12': '#070C18', '#10131A': '#0E1830', '#161A23': '#121F3C',
    '#3B82F6': '#4C7DFF', '#2563EB': '#6B95FF', '#E2E8F0': '#E6EBF7',
    '#94A3B8': '#8C9ABC', '#EF4444': '#E86A62', '#22C55E': '#3ECF8E',
    '#C8D6E5': '#E6EBF7', '#CBD5E1': '#E6EBF7', '#FCA5A5': '#E86A62',
    '#E5E7EB': '#E6EBF7', '#8B5CF6': '#6B95FF', '#2BCB6A': '#3ECF8E',
    '#38EF7D': '#3ECF8E', '#F59E0B': '#E5AC3A', '#A5B4FC': '#8C9ABC',
    '#6366F1': '#4C7DFF', '#0B0F1A': '#070C18', '#34D399': '#3ECF8E',
    '#F0B84D': '#E5AC3A', '#0B1428': '#070C18', '#1A1206': '#070C18',
    '#9CA3AF': '#8C9ABC', '#93C5FD': '#6B95FF', '#6EE7B7': '#3ECF8E',
    '#E4E6EB': '#E6EBF7', '#4F46E5': '#4C7DFF', '#1E3A2E': '#121F3C',
    '#7C3AED': '#4C7DFF', '#FCD34D': '#E5AC3A', '#3B1E1E': '#1C2B4F',
    '#3B2F1E': '#1C2B4F', '#10B981': '#3ECF8E', '#222636': '#121F3C',
    '#818CF8': '#6B95FF', '#0F1117': '#070C18', '#2D3142': '#121F3C',
    '#C7D2FE': '#E6EBF7', '#1E293B': '#121F3C', '#1A1D29': '#121F3C',
}

templates = [
    'templates/prep/probe.html',
    'templates/daily_tasks/daily_tasks_dashboard.html',
    'templates/olympiad/method.html',
    'templates/olympiad/method_task.html',
]

emoji_pattern = re.compile('[\U0001F300-\U0001FAFF\u2600-\u27BF\u2700-\u27BF]')

for t in templates:
    if not os.path.exists(t):
        print(t, 'NOT FOUND')
        continue
    with open(t, 'r', encoding='utf-8') as f:
        content = f.read()
    
    for old, new in REPLACE.items():
        content = content.replace(old, new)
        content = content.replace(old.lower(), new.lower())
    
    content = re.sub(r'(?<!rgba\()#FFFFFF(?![\da-fA-F])', '#E6EBF7', content, flags=re.IGNORECASE)
    content = re.sub(r'(?<!rgba\()#FFF\b(?![\da-fA-F])', '#E6EBF7', content, flags=re.IGNORECASE)
    
    content = emoji_pattern.sub('', content)
    
    with open(t, 'w', encoding='utf-8') as f:
        f.write(content)
    
    with open(t, 'r', encoding='utf-8') as f:
        v = f.read()
    hexes = set(m.upper() for m in re.findall(r'#[0-9A-Fa-f]{6}', v))
    foreign = hexes - ALLOWED
    emojis = emoji_pattern.findall(v)
    status = 'OK' if not foreign and not emojis else 'STILL_ISSUES'
    print('{} {} FOREIGN={} EMOJI={}'.format(t, status, len(foreign), len(emojis)))
