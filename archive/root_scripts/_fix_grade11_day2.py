#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix grade 11 Day 2 problems - extract from saved response and inject into olympiads.py
"""
import json
import sys
import os

os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

# Step 1: Read the raw response
with open('_last_response_11.txt', 'r', encoding='utf-8') as f:
    raw = f.read()

print(f"Raw response length: {len(raw)} bytes")

# Step 2: Extract JSON array - find first [ and last ]
start = raw.find('[')
end = raw.rfind(']')
print(f"JSON array from pos {start} to {end}")

if start < 0 or end <= start:
    print("ERROR: Could not find JSON array markers!")
    sys.exit(1)

json_str = raw[start:end+1]

# Step 3: Parse JSON
try:
    day2_problems = json.loads(json_str)
    print(f"Parsed {len(day2_problems)} problems from DeepSeek response")
except json.JSONDecodeError as e:
    print(f"ERROR parsing JSON: {e}")
    # Try to save the raw JSON string for inspection
    with open('_grade11_json_str.txt', 'w', encoding='utf-8') as f:
        f.write(json_str[:5000])
    print("Saved first 5000 chars to _grade11_json_str.txt")
    sys.exit(1)

# Step 4: Load the current olympiads data
# The file was saved as JSON: OLYMPIADS_DB = [...]
# We need to load the JSON part
with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the JSON array in the file
start = content.find('[')
end = content.rfind(']')
if start < 0 or end <= start:
    print("ERROR: Could not find JSON array in olympiads.py!")
    sys.exit(1)

all_entries = json.loads(content[start:end+1])
print(f"Loaded {len(all_entries)} entries from olympiads.py")

# Step 5: Find grade 11 entry (index 1046)
idx = 1046
entry = all_entries[idx]
existing_problems = entry.get('problems', [])
print(f"\nEntry index {idx}: grade={entry.get('grade')}, round={entry.get('round')}")
print(f"  Existing problems: {len(existing_problems)}")
print(f"  Problems have 'day' field: {any('day' in p for p in existing_problems)}")

# Step 6: Add day=1 to existing problems
for p in existing_problems:
    if 'day' not in p:
        p['day'] = 1

# Step 7: Validate and add Day 2 problems
valid = []
for p in day2_problems:
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

# Step 8: Save back
output = 'OLYMPIADS_DB = ' + json.dumps(all_entries, ensure_ascii=False, indent=2)
output += '\n'

# Backup first
import shutil
if os.path.exists('olympiads.py'):
    shutil.copy2('olympiads.py', 'olympiads_backup_after_3grades.py')
    print("\nBackup saved as olympiads_backup_after_3grades.py")

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
    shutil.copy2(db_py_path, db_py_path + '.bak2')
    with open(db_py_path, 'w', encoding='utf-8') as f:
        f.write(db_content)
    print(f"Updated {db_py_path}")

# Step 9: Verify by re-reading
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
    print(f"  num={p.get('num')}, day={p.get('day')}, text={p.get('text','')[:50]}...")

print("\nDone! All 4 vsosh 2020 regional entries now have Day 2 problems.")
