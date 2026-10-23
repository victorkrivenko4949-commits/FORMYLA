#!/usr/bin/env python3
import json, re, os

# Search for bare #\text (without escape) in all data files
files_to_check = [
    'secrets_dump.json',
    'data/olympiads/methods_catalog_105.json',
    'data/olympiads/methods_catalog_89.json',
]

for filepath in files_to_check:
    if not os.path.exists(filepath):
        print(f'{filepath} - not found, skipping')
        continue
    
    print(f'\n=== {filepath} ===')
    with open(filepath, 'r', encoding='utf-8') as f:
        raw = f.read()
    
    # Search for the pattern: #\text{ (bare hash followed by \text)
    # In the raw JSON, this would appear as: #\\text{ or just #\text{
    # Look for literal # character followed by backslash text
    for m in re.finditer(r'#\\\\?text\{', raw):
        start = max(0, m.start() - 50)
        end = min(len(raw), m.end() + 80)
        context = raw[start:end]
        print(f'  Found BARE #\\\\text at byte {m.start()}: ...{context!r}...')
    
    # Also search for the pattern in decoded JSON content
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            for i, entry in enumerate(data):
                for key in ['content', 'worked_example_md', 'solution_md', 'definition_md', 'metadata_md', 'triggers_md', 'pitfalls_md']:
                    val = entry.get(key, '')
                    if isinstance(val, str) and '#\\text{' in val:
                        # Found bare #\text{ in decoded content
                        idx = val.index('#\\text{')
                        start = max(0, idx - 40)
                        end = min(len(val), idx + 80)
                        snippet = val[start:end]
                        title = entry.get('title', entry.get('code', '?'))
                        print(f'\n  [{filepath}] Entry {i} ({title}) key={key}:')
                        print(f'    BARE # at pos {idx}: ...{snippet!r}...')
    except Exception as e:
        print(f'  Error decoding: {e}')
