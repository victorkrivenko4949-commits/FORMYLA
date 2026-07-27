#!/usr/bin/env python3
"""Search the CSV bank for vsosh 2020 regional 10th grade problems."""
import csv, os, json

path = r'C:\Users\Victor\Downloads\Bank_zadach_VsOSh_po_iacheikam.csv'
results = []

with open(path, 'r', encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    headers = next(reader)
    
    # Search for 2020, regional, grade 10
    for row in reader:
        row_text = ' '.join(row).lower()
        # We want 2020 regional for 10th grade
        if ('2020' in row_text or 'регион' in row_text) and ('10' in row_text or 'десятый' in row_text):
            results.append(row)
        elif len(results) < 5 and ('2020' in row_text and 'регион' in row_text):
            results.append(row)
        
        if len(results) >= 20:
            break

with open('_diag_csv_search.txt', 'w', encoding='utf-8') as out:
    out.write(f'Headers ({len(headers)}): {headers}\n')
    out.write(f'Found {len(results)} matching rows\n')
    for i, row in enumerate(results):
        out.write(f'\n--- Row {i} ---\n')
        for j, (h, val) in enumerate(zip(headers, row)):
            out.write(f'  [{j}] {h}: {val[:200] if val else "(empty)"}\n')
