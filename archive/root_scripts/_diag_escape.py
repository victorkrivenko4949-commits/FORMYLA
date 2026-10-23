# -*- coding: utf-8 -*-
"""Diagnose why specific text replacements fail in apply_fixes_to_file."""
import sys, re

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

# Load olympiads.py content
with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Cases that failed (from the output)
failed_cases = [
    # Type E: Find all variations of "Найдите все вещественные решения системы уравнений"
    ("\u5926\u2726\u2723\u2724", "PUA chars"),
    # Type D: "Дан многочлен" with set# formula_unity (empty set_id)
    ("formula_unity", "Type D"),
    # Type D: lomonosov
    ("lomonosov", "Type D lomonosov"),
    # Type E phystech
    ("phystech", "Type E phystech"),
    # Type E pvg
    ("pvg", "Type E pvg"),
    # "Дан многочлен" in raw content
    ("Дан многочлен", "multi polynomial"),
]

print("=== Searching for 'Дан многочлен' in olympiads.py ===")
count = content.count('Дан многочлен')
print(f"Found {count} occurrences")

# Show a few with context
for i, m in enumerate(re.finditer('Дан многочлен', content)):
    if i >= 3:
        break
    start = max(0, m.start() - 10)
    end = min(len(content), m.end() + 200)
    snippet = content[start:end]
    print(f"\n--- Occurrence {i+1} at pos {m.start()} ---")
    repr_snippet = repr(snippet)
    print(repr_snippet)

print("\n\n=== Searching for 'Найдите все вещественные решения' ===")
count2 = content.count('Найдите все вещественные решения')
print(f"Found {count2} occurrences")

for i, m in enumerate(re.finditer('Найдите все вещественные решения', content)):
    if i >= 3:
        break
    start = max(0, m.start() - 10)
    end = min(len(content), m.end() + 200)
    snippet = content[start:end]
    print(f"\n--- Occurrence {i+1} at pos {m.start()} ---")
    print(repr(snippet))

# Check what the actual text field value is for the lomonosov set# entries
print("\n\n=== Check parsed text for lomonosov sets ===")
for i, s in enumerate(oly.PROBLEMS_DB):
    if 'lomonosov' in str(s.get('source', '')).lower() or 'лomonosov' in str(s.get('olympiad_title', '')).lower():
        text = s.get('text', '')
        if 'Дан многочлен' in text or len(text) < 100:
            print(f"\n  set#{s.get('set_id','')} prob#{s.get('problem_num','')}:")
            print(f"    olympiad: {s.get('olympiad_title','')}")
            print(f"    text ({len(text)} chars): {repr(text[:120])}...")

print("\n\nDone")
