#!/usr/bin/env python3
"""Fix unterminated string literal on line 25 of olympiads.py."""
import sys

PATH = 'olympiads.py'

with open(PATH, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
print(f"Line 25 (1-based) content: {repr(lines[24])}")
print(f"Line 25 ends with single quote: {lines[24].rstrip().endswith(chr(39))}")

if not lines[24].rstrip().endswith("'"):
    # Add closing quote before the newline
    old = lines[24]
    lines[24] = old.rstrip('\n\r') + "'\n"
    print(f"Fixed to: {repr(lines[24])}")

    with open(PATH, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("File written successfully!")
else:
    print("Line 25 already has closing quote - no fix needed.")

# Verify
import ast
try:
    with open(PATH, 'r', encoding='utf-8') as f:
        ast.parse(f.read())
    print("VERIFICATION PASSED: File parses without SyntaxError!")
except SyntaxError as e:
    print(f"VERIFICATION FAILED: {e}")
    sys.exit(1)
