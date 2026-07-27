#!/usr/bin/env python3
"""Fix syntax errors in olympiads.py after null byte removal"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))

with open('olympiads.py', 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.split('\n')

fixed = 0
for i, line in enumerate(lines):
    stripped = line.strip()
    # If line starts with a quote but doesn't end with one (single quote only)
    if stripped.startswith("'") and not stripped.endswith("'") and not stripped.endswith(",\\"):
        if stripped.count("'") == 1:  # only opening quote
            lines[i] = line + "'"
            print(f"Fixed line {i+1}: added missing closing quote")
            fixed += 1

text = '\n'.join(lines)

with open('olympiads.py', 'w', encoding='utf-8') as f:
    f.write(text)

print(f"Fixed {fixed} lines")

# Now verify
try:
    compile(text, 'olympiads.py', 'exec')
    print("COMPILE: OK!")
except SyntaxError as e:
    print(f"Still has syntax error at line {e.lineno}: {e.msg}")
    if e.lineno:
        err_line = lines[e.lineno - 1] if e.lineno - 1 < len(lines) else "N/A"
        print(f"Content: {err_line[:200]}")
