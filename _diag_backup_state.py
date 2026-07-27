#!/usr/bin/env python3
"""Check backup state of idx 1042 and CSV headers."""
import ast, csv, os, sys

OUT = sys.stdout

# 1. Check backup
OUT.write("=== BACKUP CHECK ===\n")
with open('olympiads_backup_g10v2_fix.py', 'r', encoding='utf-8') as f:
    data = f.read()
tree = ast.parse(data)
db = ast.literal_eval(tree.body[0].value)
entry = db[1042]
OUT.write(f'Backup idx 1042: {len(entry["problems"])} problems\n')
for p in entry['problems']:
    OUT.write(f'  Problem {p["num"]} (day={p.get("day","?")})\n')

# 2. Check CSV
OUT.write("\n=== CSV CHECK ===\n")
path = r'C:\Users\Victor\Downloads\Bank_zadach_VsOSh_po_iacheikam.csv'
if os.path.exists(path):
    OUT.write(f'CSV exists at: {path}\n')
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        headers = next(reader)
        OUT.write(f'Headers ({len(headers)}): {headers}\n')
        for i, row in enumerate(reader):
            if i < 10:
                OUT.write(f'Row {i}: cols={len(row)} first={str(row[:4])[:200]}\n')
            else:
                break
else:
    OUT.write(f'CSV NOT found at {path}\n')
    # Try alternative locations
    for p in [r'C:\Users\Victor\Downloads', os.path.expanduser('~/Downloads')]:
        if os.path.exists(p):
            for fname in os.listdir(p):
                if 'bank' in fname.lower() or 'vsosh' in fname.lower() or 'задач' in fname.lower():
                    OUT.write(f'  Found: {os.path.join(p, fname)}\n')
