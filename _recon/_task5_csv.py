# -*- coding: utf-8 -*-
"""Task 5: Catalog CSV export."""
import json, os, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cat_path = os.path.join(BASE, 'data', 'olympiads', 'methods_catalog_105.json')
csv_path = os.path.join(BASE, '_recon', 'methods_flat.csv')

with open(cat_path, 'r', encoding='utf-8') as f:
    catalog = json.load(f)

with open(csv_path, 'w', encoding='utf-8-sig', newline='') as csvf:
    csvf.write('method_code,method_name,section,grades,recommended_competitions\n')
    for m in catalog:
        code = m.get('method_code', '?')
        name = (m.get('method_name', '?') or '').replace('"', '""')
        section = str(m.get('section', '')).replace('"', '""')
        grades = m.get('grades', [])
        if isinstance(grades, list):
            grades_str = str(grades)
        else:
            grades_str = str(grades)
        comps = m.get('recommended_competitions', '')
        if not comps:
            comps = str(m.get('frequency_vsosh_9', ''))
        if isinstance(comps, list):
            comps = ', '.join(str(c) for c in comps)
        comps = str(comps).replace('"', '""')
        csvf.write(f'{code},"{name}","{section}","{grades_str}","{comps}"\n')

print(f'CSV written: {csv_path}')
print(f'Total entries: {len(catalog)}')

# Print all 102 rows
with open(csv_path, 'r', encoding='utf-8-sig') as f:
    print(f.read())
