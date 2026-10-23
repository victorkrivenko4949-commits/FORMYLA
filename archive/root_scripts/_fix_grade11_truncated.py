#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix grade 11 Day 2 - the DeepSeek response was truncated (no closing ]).
Try to salvage by appending ] and parsing, or extract complete objects.
"""
import json
import sys
import os

os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

# Read the raw response
with open('_last_response_11.txt', 'rb') as f:
    raw_bytes = f.read()

# Try to decode and find content
raw = raw_bytes.decode('utf-8', errors='replace')

print(f"Raw response length: {len(raw_bytes)} bytes")

# Strategy 1: Try appending ] and parse
json_str = raw + ']'
# But first, find the [ to make sure we start at the right place
start = raw.find('[')
if start >= 0:
    json_str = raw[start:] + ']'

try:
    data = json.loads(json_str)
    print(f"Strategy 1 succeeded! Parsed {len(data)} problems")
except json.JSONDecodeError as e:
    print(f"Strategy 1 failed: {e}")
    
    # Strategy 2: Find complete problem objects
    # Each problem starts with {"num": and ends with },
    print("\nStrategy 2: Extract complete problem objects...")
    
    # Find all problem-like objects
    problems = []
    pos = start
    while pos >= 0:
        obj_start = raw.find('{', pos)
        if obj_start < 0:
            break
        
        # Try to find the matching } for this object
        depth = 0
        obj_end = -1
        for i in range(obj_start, len(raw)):
            if raw[i] == '{':
                depth += 1
            elif raw[i] == '}':
                depth -= 1
                if depth == 0:
                    obj_end = i
                    break
        
        if obj_end < 0:
            print(f"  Incomplete object at position {obj_start}, stopping")
            break
        
        obj_str = raw[obj_start:obj_end+1]
        
        try:
            obj = json.loads(obj_str)
            problems.append(obj)
            print(f"  Found problem num={obj.get('num')}: text={obj.get('text','')[:50]}...")
        except json.JSONDecodeError:
            # Try to find num and text/answer fields manually
            print(f"  Cannot parse object at {obj_start}, might have truncated fields")
            # Try to extract what we can
            num_match = __import__('re').search(r'"num"\s*:\s*(\d+)', obj_str)
            if num_match:
                num = int(num_match.group(1))
                # Try to extract text field
                text_match = __import__('re').search(r'"text"\s*:\s*"(.+?)"(?=,\s*"|,\s*$|\s*})', obj_str)
                answer_match = __import__('re').search(r'"answer"\s*:\s*"(.+?)"(?=,\s*"|,\s*$|\s*})', obj_str)
                partial = {'num': num}
                if text_match:
                    partial['text'] = text_match.group(1)
                if answer_match:
                    partial['answer'] = answer_match.group(1)
                partial['solution'] = ''  # Truncated
                problems.append(partial)
                print(f"  Partial problem num={num}: text={partial.get('text','')[:50]}...")
            break
        
        pos = obj_end + 1
        # Skip commas and whitespace
        while pos < len(raw) and raw[pos] in ',\n\r\t ':
            pos += 1
    
    print(f"\nExtracted {len(problems)} problems total")
    
    if len(problems) >= 5:
        data = problems
    else:
        print(f"Only got {len(problems)} problems, need 5")
        sys.exit(1)

# Now inject into olympiads.py
with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()

start = content.find('[')
end = content.rfind(']')
if start < 0 or end <= start:
    print("ERROR: Could not find JSON array in olympiads.py!")
    sys.exit(1)

all_entries = json.loads(content[start:end+1])
print(f"\nLoaded {len(all_entries)} entries from olympiads.py")

# Find grade 11 entry (index 1046)
idx = 1046
entry = all_entries[idx]
existing_problems = entry.get('problems', [])
print(f"\nEntry index {idx}: grade={entry.get('grade')}, round={entry.get('round')}")
print(f"  Existing problems: {len(existing_problems)}")
print(f"  Problems have 'day' field: {any('day' in p for p in existing_problems)}")

# Add day=1 to existing problems
for p in existing_problems:
    if 'day' not in p:
        p['day'] = 1

# Validate and add Day 2 problems
valid = []
for p in data:
    if not isinstance(p, dict):
        continue
    num = p.get('num', 0)
    if isinstance(num, int) and 6 <= num <= 10:
        valid.append(p)
    else:
        print(f"  Skipping problem with num={num}")

# If we got less than 5, renumber
if len(valid) < 5:
    print(f"WARNING: Only got {len(valid)} valid problems, renumbering")
    for i, p in enumerate(valid):
        p['num'] = 6 + i

print(f"  Valid Day 2 problems: {len(valid)}")

# Add day=2 and required fields
for p in valid:
    p['day'] = 2
    p.setdefault('answer', '')
    p.setdefault('solution', '')
    p.setdefault('solution_status', '')
    p.setdefault('text', '')

# Append to existing
existing_problems.extend(valid)
print(f"  Total problems now: {len(existing_problems)}")
print(f"  Day 1: {sum(1 for p in existing_problems if p.get('day')==1)}")
print(f"  Day 2: {sum(1 for p in existing_problems if p.get('day')==2)}")

# Save back
output = 'OLYMPIADS_DB = ' + json.dumps(all_entries, ensure_ascii=False, indent=2)
output += '\n'

import shutil
if os.path.exists('olympiads.py'):
    shutil.copy2('olympiads.py', 'olympiads_backup_before_grade11.py')
    print("\nBackup saved as olympiads_backup_before_grade11.py")

with open('olympiads.py', 'w', encoding='utf-8') as f:
    f.write(output)
print(f"Written olympiads.py ({len(output)} bytes)")

# Also update data/olympiads_db.py
db_py_path = 'data/olympiads_db.py'
if os.path.exists(db_py_path):
    db_content = '# -*- coding: utf-8 -*-\n'
    db_content += '# Extracted from routes/olympiad.py for reuse by the olympiad Blueprint.\n'
    db_content += '# This file contains only the OLYMPIADS_DB data dictionary.\n\n'
    db_content += 'OLYMPIADS_DB = ' + json.dumps(all_entries, ensure_ascii=False, indent=2)
    db_content += '\n'
    shutil.copy2(db_py_path, db_py_path + '.bak3')
    with open(db_py_path, 'w', encoding='utf-8') as f:
        f.write(db_content)
    print(f"Updated {db_py_path}")

# Verify by re-reading
print("\n=== VERIFICATION ===")
with open('olympiads.py', 'r', encoding='utf-8') as f:
    verify_content = f.read()
verify_start = verify_content.find('[')
verify_end = verify_content.rfind(']')
verify_data = json.loads(verify_content[verify_start:verify_end+1])
entry = verify_data[1046]
probs = entry.get('problems', [])
print(f"Entry 1046 problems: {len(probs)}")
for p in probs:
    print(f"  num={p.get('num')}, day={p.get('day')}, text={p.get('text','')[:60]}...")

print("\nDone! Grade 11 Day 2 problems injected.")
