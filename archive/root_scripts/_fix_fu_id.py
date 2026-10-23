import json

JSONL_PATH = r'C:\Users\Victor\Downloads\olympiad_DB_final_fixed.jsonl'

# Load all entries, find max id globally
entries = []
max_id = 0
with open(JSONL_PATH, 'r', encoding='utf-8') as f:
    for line in f:
        entry = json.loads(line)
        entries.append(entry)
        eid = entry.get('id', '')
        if eid:
            try:
                eid_int = int(eid)
                if eid_int > max_id:
                    max_id = eid_int
            except:
                pass

print(f"Total entries: {len(entries)}")
print(f"Global max id: {max_id}")

# Find the formula_unity 2022 grade 6 final entry
target = None
target_idx = None
for i, entry in enumerate(entries):
    if (entry.get('olympiad') == 'formula_unity' and 
        str(entry.get('year', '')) == '2022' and 
        str(entry.get('grade', '')) == '6' and
        entry.get('round') == 'final'):
        target = entry
        target_idx = i
        break

if target:
    print(f"\nFound target entry at index {target_idx}")
    print(f"Current id: {target.get('id', 'N/A')!r}")
    new_id = max_id + 1
    print(f"Assigning new id: {new_id}")
    target['id'] = str(new_id)
    
    # Also fix _olympiad_id which is also empty
    target['_olympiad_id'] = str(new_id)
    
    # Write back
    with open(JSONL_PATH, 'w', encoding='utf-8') as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    
    print(f"Updated! New id assigned: {new_id}")
    
    # Verify
    print(f"\nVerification: id={target.get('id')!r}")
else:
    print("Target not found!")
