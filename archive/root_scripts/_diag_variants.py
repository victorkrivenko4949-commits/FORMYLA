#!/usr/bin/env python3
"""Check variant 1 problems for comparison."""
import ast, json

with open('olympiads.py', 'r', encoding='utf-8') as f:
    data = f.read()
tree = ast.parse(data)
db = ast.literal_eval(tree.body[0].value)

# Variant 1 (idx 1041)
entry1 = db[1041]
probs1 = entry1['problems']
lines = [f'Variant 1 (idx 1041): {len(probs1)} problems']
for p in probs1:
    lines.append(f'  Problem {p["num"]} (day={p.get("day")}): text[:120]={p["text"][:120]}')

# Variant 2 (idx 1042)  
entry2 = db[1042]
probs2 = entry2['problems']
lines.append(f'\nVariant 2 (idx 1042): {len(probs2)} problems')
for p in probs2:
    lines.append(f'  Problem {p["num"]} (day={p.get("day")}): text[:120]={p["text"][:120]}')

# Check bank_zadach_VsOSh (if present in downloads)
import os
bank_path = os.path.expanduser('~/Downloads/Bank_zadach_VsOSh_po_iacheikam.csv')
if os.path.exists(bank_path):
    lines.append(f'\nBank_zadach_VsOSh exists at: {bank_path}')
else:
    lines.append('\nBank_zadach_VsOSh not found')

with open('_diag_variants.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print('OK')
