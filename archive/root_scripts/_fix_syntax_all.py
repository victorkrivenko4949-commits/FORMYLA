#!/usr/bin/env python3
"""Fix all unterminated string literals in olympiads.py - writes immediately after each fix."""
import ast
import sys
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PATH = 'olympiads.py'

with open(PATH, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
fix_count = 0

for i, line in enumerate(lines):
    stripped = line.rstrip('\n\r')
    
    # Case 1: Line starts with ' (opening a string) but doesn't end with '
    if stripped.lstrip().startswith("'") and not stripped.endswith("'"):
        lines[i] = stripped + "'\n"
        fix_count += 1
        # Write immediately
        with open(PATH, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f"Line {i+1}: unterminated -> fixed")
    
    # Case 2: Line has a closing ' but is missing opening quote (e.g., Ответ: могут.',)
    elif not stripped.lstrip().startswith("'") and stripped.rstrip(',').endswith("'"):
        idx = stripped.rfind("'")
        if idx > 0:
            rest = stripped[idx+1:]
            if rest in ('', ',', ' ', '  ', '   '):
                # Add opening quote
                lines[i] = "'" + stripped + "\n"
                fix_count += 1
                # Write immediately
                with open(PATH, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                print(f"Line {i+1}: missing opening quote -> fixed")

if fix_count == 0:
    print("No issues found!")
else:
    print(f"\nApplied {fix_count} fixes total!")

# Final verification
try:
    with open(PATH, 'r', encoding='utf-8') as f:
        ast.parse(f.read())
    print("VERIFICATION PASSED: File parses without SyntaxError!")
except SyntaxError as e:
    print(f"VERIFICATION FAILED at line {e.lineno}: {e.msg}")
    if e.lineno:
        for j in range(max(0, e.lineno-3), min(len(lines), e.lineno+2)):
            marker = " >>>" if j+1 == e.lineno else "    "
            print(f"{marker} L{j+1}: {repr(lines[j][:150])}")
    sys.exit(1)
