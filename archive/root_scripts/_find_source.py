#!/usr/bin/env python
import json, os

# Check pre_live file
prelive_path = r'C:\Users\Victor\Downloads\FORMYLA_CONDITION_COURT\runs\selection_1080_20260712_134037\curated_bank_L1_L5_pre_live.json'
if os.path.exists(prelive_path):
    with open(prelive_path, 'r', encoding='utf-8') as f:
        prelive = json.load(f)
    print(f'pre_live: {len(prelive)} tasks')
    print(f'pre_live[0] keys: {list(prelive[0].keys())[:15]}')
else:
    print(f'pre_live NOT FOUND at {prelive_path}')

# Search for files that might be the 1080 selection source
search_dirs = [
    r'C:\Users\Victor\Downloads',
    r'C:\Users\Victor\Desktop\Новая папка (2)',
]

for d in search_dirs:
    if os.path.exists(d):
        for f in os.listdir(d):
            if 'selection' in f.lower() or '1080' in f or 'sel1080' in f.lower():
                print(f'Found: {os.path.join(d, f)}')
