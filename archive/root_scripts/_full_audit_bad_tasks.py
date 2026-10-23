"""
Full audit of olympiads.py: find ALL problems with bad/stub/truncated/corrupted text fields.
Output: detailed JSON report for planning.
"""
import re
import json
import sys

FILE = 'olympiads.py'
OUTPUT = 'c:/Users/Victor/Desktop/full_bad_tasks_audit.json'

with open(FILE, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"File has {len(lines)} lines")

# Strategy: find each 'text': '...' or "text": '...' pattern line by line
# Then look ahead to see if it's a short stub or continues with concatenation

bad_texts = []
current_text = None
current_line = None
current_num = None

# Also track olympiad set boundaries (id = NNN)
current_set_id = None

for lineno, line in enumerate(lines, 1):
    # Detect set ID: e.g. 'id': 691,
    m = re.search(r"'id':\s*(\d+)", line)
    if m:
        current_set_id = int(m.group(1))
    
    # Detect problem num: 'num': N,
    m = re.search(r"'num':\s*(\d+)", line)
    if m:
        current_num = int(m.group(1))
    
    # Detect 'text': '...' start
    m = re.search(r"'text':\s*'(.*)", line)
    if m:
        text_start = m.group(1)
        current_line = lineno
        current_text = text_start
        # Check if it ends on this line (with closing ')
        if text_start.endswith("',"):
            text_val = text_start[:-2]  # remove trailing ',
            if len(text_val.strip()) < 50:
                bad_texts.append({
                    'line': current_line,
                    'set_id': current_set_id,
                    'num': current_num,
                    'text_preview': text_val[:120],
                    'length': len(text_val)
                })
            current_text = None
        # Otherwise it continues with concatenation

print(f"\n=== BAD TEXTS FOUND: {len(bad_texts)} ===")

# Group by type
stub_types = {}
for bt in bad_texts:
    t = bt['text_preview']
    if 'Решение не найдено' in t:
        key = 'Решение не найдено'
    elif re.match(r'Задача \d+ \(вариант \d+\)', t):
        key = 'Задача N (вариант M)'
    elif len(t) < 10:
        key = f'ultra_short({len(t)})'
    else:
        key = 'other_short'
    
    stub_types.setdefault(key, []).append(bt)

print("\nBreakdown:")
for key, items in sorted(stub_types.items(), key=lambda x: -len(x[1])):
    print(f"  {key}: {len(items)}")
    for item in items[:5]:
        print(f"    line {item['line']:>6} | set={item['set_id']} num={item['num']} | {item['text_preview'][:80]}")

# Find sets with most bad problems
from collections import Counter
set_counts = Counter(bt['set_id'] for bt in bad_texts if bt['set_id'])
print(f"\nSets with most bad problems:")
for sid, cnt in set_counts.most_common(20):
    print(f"  set {sid}: {cnt} bad problems")

# Save
with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump({
        'total_bad': len(bad_texts),
