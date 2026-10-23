#!/usr/bin/env python
"""
Analyze curated bank with subtopics from source dataset.
Count grade|level|subtopic cells for L1-L3 target matrix.
"""
import json
import sys
from collections import defaultdict

BANK_PATH = 'curated_bank_L1_L5_fixed.json'
SOURCE_PATH = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_completed.json'

TARGET_GRADES = {2, 5, 6, 7, 8, 9, 10, 11}
TARGET_LEVELS = {1, 2, 3}

# 1. Load bank
with open(BANK_PATH, 'r', encoding='utf-8') as f:
    bank = json.load(f)
print(f'Bank: {len(bank)} tasks')

# 2. Load source
try:
    with open(SOURCE_PATH, 'r', encoding='utf-8') as f:
        source = json.load(f)
    print(f'Source: {len(source)} tasks')
    source_has_subtopic = 'subtopic' in source[0] if source else False
    print(f'Source has subtopic field: {source_has_subtopic}')
    if source_has_subtopic:
        subtopics = set(t.get('subtopic', '') for t in source)
        print(f'Unique subtopics in source: {len(subtopics)}')
        # Show some
        st_list = sorted(subtopics)[:20]
        print(f'First 20: {st_list}')
except FileNotFoundError:
    print(f'Source file not found: {SOURCE_PATH}')
    source = []
    source_has_subtopic = False

# 3. Check bank fields
print(f'\nBank task[0] keys: {list(bank[0].keys())}')
print(f'Bank has subtopic field: {"subtopic" in bank[0]}')

# 4. Try to map by source_index
if source and source_has_subtopic:
    # Build source index
    source_by_idx = {}
    for t in source:
        idx = t.get('source_index')
        if idx is not None:
            source_by_idx[idx] = t
    
    print(f'\nSource indexed by source_index: {len(source_by_idx)} tasks')
    
    # Also check original_id
    source_by_oid = {}
    for t in source:
        oid = t.get('original_id')
        if oid:
            source_by_oid[oid] = t
    print(f'Source indexed by original_id: {len(source_by_oid)} tasks')
    
    # Try mapping bank tasks
    mapped_by_idx = 0
    mapped_by_oid = 0
    for bt in bank:
        idx = bt.get('source_index')
        oid = bt.get('original_id')
        if idx is not None and idx in source_by_idx:
            mapped_by_idx += 1
        if oid and oid in source_by_oid:
            mapped_by_oid += 1
    
    print(f'Bank tasks mapped by source_index: {mapped_by_idx}/{len(bank)}')
    print(f'Bank tasks mapped by original_id: {mapped_by_oid}/{len(bank)}')
    
    # Use whichever maps better
    if mapped_by_idx >= mapped_by_oid:
        print('\nUsing source_index mapping')
        source_lookup = source_by_idx
        mapped_count = mapped_by_idx
    else:
        print('\nUsing original_id mapping')
        source_lookup = source_by_oid
        mapped_count = mapped_by_oid
    
    # Now count grade|level|subtopic cells for L1-L3 target tasks
    gls_cells = defaultdict(list)  # (grade, level, subtopic) -> [tasks]
    gl_cells = defaultdict(list)   # (grade, level) -> [tasks]
    unmapped = []
    no_subtopic = []
    
    for bt in bank:
        g = bt.get('grade')
        l = bt.get('level')
        if g not in TARGET_GRADES or l not in TARGET_LEVELS:
            continue
        
        gl_cells[(g, l)].append(bt)
        
        # Try to find subtopic
        idx = bt.get('source_index')
        oid = bt.get('original_id')
        
        st = None
        if idx is not None and idx in source_by_idx:
            st = source_by_idx[idx].get('subtopic')
        elif oid and oid in source_by_oid:
            st = source_by_oid[oid].get('subtopic')
        
        if st is None:
            unmapped.append((g, l))
            st = '__UNMAPPED__'
        elif not st or st.strip() == '':
            no_subtopic.append((g, l))
            st = '__NO_SUBTOPIC__'
        
        gls_cells[(g, l, st)].append(bt)
    
    print(f'\n=== L1-L3 Target Matrix ===')
    print(f'Target grades: {sorted(TARGET_GRADES)}')
    print(f'Target levels: {sorted(TARGET_LEVELS)}')
    print(f'Expected cells: {len(TARGET_GRADES) * len(TARGET_LEVELS)} = 24')
    print(f'Total L1-L3 target tasks: {sum(len(v) for v in gl_cells.values())}')
    
    # Grade|level cells
    print(f'\n--- Grade|Level cells ({len(gl_cells)} occupied out of 24): ---')
    for k in sorted(gl_cells.keys()):
        print(f'  G{k[0]}|L{k[1]}: {len(gl_cells[k])} tasks')
    
    missing_gl = set()
    for g in sorted(TARGET_GRADES):
        for l in sorted(TARGET_LEVELS):
            if (g, l) not in gl_cells:
                missing_gl.add((g, l))
    print(f'Missing grade|level cells: {len(missing_gl)}')
    for g, l in sorted(missing_gl):
        print(f'  G{g}|L{l}')
    
    # Grade|level|subtopic cells
    print(f'\n--- Grade|Level|Subtopic cells: ---')
    gls_sorted = sorted(gls_cells.keys())
    print(f'Total unique (grade, level, subtopic) cells: {len(gls_sorted)}')
    
    for k in gls_sorted:
        g, l, st = k
        tasks = gls_cells[k]
        if st.startswith('__'):
            print(f'  G{g}|L{l}|{st}: {len(tasks)} tasks')
        else:
            print(f'  G{g}|L{l}|{st}: {len(tasks)} tasks')
    
    # Count how many subtopics per grade|level
    print(f'\n--- Subtopics per grade|level cell: ---')
    gl_to_subtopics = defaultdict(set)
    for (g, l, st), tasks in gls_cells.items():
        if not st.startswith('__'):
            gl_to_subtopics[(g, l)].add(st)
    
    for k in sorted(gl_to_subtopics.keys()):
        print(f'  G{k[0]}|L{k[1]}: {len(gl_to_subtopics[k])} unique subtopics')
    
    # Count perfect subtopic cells (5 tasks)
    perfect = sum(1 for k, v in gls_cells.items() if len(v) == 5 and not k[2].startswith('__'))
    underfilled = sum(1 for k, v in gls_cells.items() if 0 < len(v) < 5 and not k[2].startswith('__'))
    unmapped_cells = sum(1 for k, v in gls_cells.items() if k[2].startswith('__'))
    
    print(f'\n--- Subtopic cell quality: ---')
    print(f'Perfect (5 tasks): {perfect}')
    print(f'Underfilled (1-4 tasks): {underfilled}')
    print(f'Unmapped/no-subtopic cells: {unmapped_cells}')
    print(f'Total subtopic cells: {len(gls_sorted)}')
    
    if unmapped:
        print(f'\nUnmapped tasks: {len(unmapped)}')
    if no_subtopic:
        print(f'Tasks with empty subtopic: {len(no_subtopic)}')
    
    # Also show theme if available
    source_has_theme = 'theme' in source[0] if source else False
    print(f'\nSource has theme field: {source_has_theme}')

else:
    print('\nCannot analyze subtopics - source file not available or has no subtopic field.')
    print(f'Source file exists: {source != []}')
    print(f'Source has subtopic: {source_has_subtopic if source else "N/A"}')
    
    # Check alternative source files
    import glob
    alt_sources = glob.glob(r'C:\Users\Victor\Downloads\*5levels*')
    print(f'\nAlternative source files found: {alt_sources}')
