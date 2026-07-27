# -*- coding: utf-8 -*-
"""Diagnose why specific text replacements fail - output safe repr() only."""
import sys, re, json

sys.path.insert(0, '.')
import olympiads as oly

def _escape_py_string(text: str) -> str:
    result = []
    for ch in text:
        if ch == '\\':
            result.append('\\\\')
        elif ch == "'":
            result.append("\\'")
        elif ch == '\n':
            result.append('\\n')
        elif ch == '\r':
            result.append('\\r')
        elif ch == '\t':
            result.append('\\t')
        elif ord(ch) < 32:
            result.append(f'\\x{ord(ch):02x}')
        else:
            result.append(ch)
    return ''.join(result)

with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find specific failing case: set#46 prob#5 with "Найдите все вещественные решения"
results = []

# Search for the лomonosov set with "Дан многочлен" and empty set_id
for i, s in enumerate(oly.PROBLEMS_DB):
    text = s.get('text', '')
    sid = s.get('set_id', '')
    pnum = s.get('problem_num', '')
    
    # Case 1: lomonosov with "Дан многочлен" (Type D, empty set_id)
    if 'Дан многочлен' in text and sid == '':
        file_old = _escape_py_string(text)
        # Look for this in file
        pos = content.find(file_old)
        results.append(f"lomonosov/empty set_id prob#{pnum}:")
        results.append(f"  In file: pos={pos}")
        results.append(f"  old({len(text)}c): {repr(text[:200])}")
        results.append(f"  file_old({len(file_old)}c): {repr(file_old[:200])}")
        if pos >= 0:
            ctx = content[max(0,pos-20):pos+len(file_old)+20]
            results.append(f"  Context around match: {repr(ctx[:300])}")
        else:
            # Search for partial match
            for part in ['Дан многочлен', '*x^n', '\\dots']:
                p = content.find(part)
                if p >= 0:
                    results.append(f"  Found '{part}' at pos {p}")
                    results.append(f"    ctx: {repr(content[max(0,p-10):p+150])}")
        results.append("")
        if len([r for r in results if r.startswith("lomonosov")]) >= 3:
            break

# Case 2: set#46 with "Найдите все вещественные решения"
for i, s in enumerate(oly.PROBLEMS_DB):
    text = s.get('text', '')
    sid = s.get('set_id', '')
    pnum = s.get('problem_num', '')
    if sid == 46 and pnum == 5:
        file_old = _escape_py_string(text)
        pos = content.find(file_old)
        results.append(f"\nset#46 prob#5:")
        results.append(f"  In file: pos={pos}")
        results.append(f"  old({len(text)}c): {repr(text[:200])}")
        results.append(f"  file_old({len(file_old)}c): {repr(file_old[:200])}")
        if pos >= 0:
            ctx = content[max(0,pos-10):pos+len(file_old)+10]
            results.append(f"  Context: {repr(ctx[:300])}")
        else:
            # Try partial search
            for part in ['Найдите все вещественные', 'системы уравнений']:
                p = content.find(part)
                if p >= 0:
                    results.append(f"  Found '{part}' at pos {p}")
                    results.append(f"    ctx: {repr(content[max(0,p-10):p+200])}")
        break

# Case 3: The 4 successful ones - confirm they still work
for i, s in enumerate(oly.PROBLEMS_DB):
    text = s.get('text', '')
    if 'См. задачу R10.4' in text:
        file_old = _escape_py_string(text)
        pos = content.find(file_old)
        results.append(f"\nR10.4 reference (should succeed):")
        results.append(f"  In file: pos={pos}")
        results.append(f"  old: {repr(text[:120])}")
        if pos >= 0:
            ctx = content[max(0,pos-10):pos+len(file_old)+10]
            results.append(f"  Context: {repr(ctx[:200])}")
        break

# Write safe output
with open('_diag_results2.txt', 'w', encoding='ascii') as f:
    f.write('\n'.join(results))
print("Written to _diag_results2.txt")
