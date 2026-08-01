# -*- coding: utf-8 -*-
"""Analysis script for P1: theme_id display issue."""
import json
import sqlite3
import sys
import io

# Fix console encoding on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 1. Build theme_map from JSONL
f = open('FORMYLA_L1_L5_TOP5.jsonl', 'r', encoding='utf-8')
theme_map = {}
for line in f:
    d = json.loads(line)
    tid = d.get('theme_id', '')
    theme = d.get('theme', '')
    if tid and tid not in theme_map:
        theme_map[tid] = {'title': theme, 'grade': d.get('grade'), 'section': d.get('section', '')}
f.close()
print(f'=== JSONL: unique theme_ids = {len(theme_map)} ===')

# Show all G9 themes
g9_themes = {k: v for k, v in theme_map.items() if k.startswith('G9_')}
print(f'G9 themes: {len(g9_themes)}')
for tid in sorted(g9_themes.keys()):
    v = g9_themes[tid]
    print(f'  {tid}: {v["title"]} [{v["section"]}]')

# 2. Check DB
c = sqlite3.connect('formyla.db')
total = c.execute('SELECT COUNT(*) FROM adaptive_tasks').fetchone()[0]
print(f'\n=== DB: total tasks = {total} ===')

# Check columns
cols = [x[1] for x in c.execute('PRAGMA table_info(adaptive_tasks)').fetchall()]
print(f'Columns with "theme": {[c for c in cols if "theme" in c.lower()]}')

# Check theme_to_section.json
with open('data/theme_to_section.json', 'r', encoding='utf-8') as f:
    t2s = json.load(f)
print(f'\n=== theme_to_section.json: {len(t2s)} mappings ===')
g9_in_t2s = {k: v for k, v in t2s.items() if k.startswith('G9_')}
for tid in sorted(g9_in_t2s.keys())[:15]:
    print(f'  {tid} -> {g9_in_t2s[tid]}')

c.close()
