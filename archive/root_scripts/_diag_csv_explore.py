#!/usr/bin/env python3
"""Explore CSV bank structure."""
import csv, os
from collections import Counter

path = r'C:\Users\Victor\Downloads\Bank_zadach_VsOSh_po_iacheikam.csv'

rows = []
with open(path, 'r', encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    headers = next(reader)
    for row in reader:
        rows.append(row)

with open('_diag_csv_explore.txt', 'w', encoding='utf-8') as out:
    out.write(f'Total rows: {len(rows)}\n')
    
    # Analyze "Ячейка" (cell) column
    cells = [r[0] for r in rows if r[0]]
    cell_counts = Counter(cells)
    out.write(f'\n=== Distinct "Ячейка" values ({len(cell_counts)}) ===\n')
    for cell, count in cell_counts.most_common(30):
        sample = next((r[2][:80] for r in rows if r[0] == cell and r[2]), '')
        out.write(f'  {cell}: {count} задач | пример: {sample}\n')
    
    # Search for 2020, regional, 10th grade related
    out.write(f'\n=== Searching for "2020" and "регион" ===\n')
    for r in rows:
        text = ' '.join(r).lower()
        if '2020' in text and 'регион' in text:
            out.write(f'  Ячейка={r[0]}, Номер={r[1]}, Условие={r[2][:150] if r[2] else ""}\n')
    
    # Search for vsosh related
    out.write(f'\n=== Searching for "всош" or "всерос" ===\n')
    count = 0
    for r in rows:
        text = ' '.join(r).lower()
        if 'всош' in text or 'всерос' in text:
            out.write(f'  Ячейка={r[0]}, Номер={r[1]}, Условие={r[2][:120] if r[2] else ""}\n')
            count += 1
            if count >= 15:
                break
    
    # Sample some random rows to see data format
    out.write(f'\n=== First 10 rows ===\n')
    for i, r in enumerate(rows[:10]):
        out.write(f'  [{i}] Ячейка={r[0]}, Номер={r[1]}, Условие={str(r[2])[:150] if len(r)>2 else ""}, Ответ={str(r[3])[:80] if len(r)>3 else ""}\n')
    
    # Last 5 rows
    out.write(f'\n=== Last 5 rows ===\n')
    for i, r in enumerate(rows[-5:]):
        idx = len(rows) - 5 + i
        out.write(f'  [{idx}] Ячейка={r[0]}, Номер={r[1]}, Условие={str(r[2])[:150] if len(r)>2 else ""}\n')
