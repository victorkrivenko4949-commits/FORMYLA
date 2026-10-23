#!/usr/bin/env python3
"""Clean null bytes from olympiads.py and verify it's valid Python"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Read as binary
with open('olympiads.py', 'rb') as f:
    raw = f.read()

null_count = raw.count(b'\x00')
print(f"Before: {len(raw)} bytes, {null_count} null bytes")

# Remove null bytes
clean = raw.replace(b'\x00', b'')

print(f"After: {len(clean)} bytes, {clean.count(b'\x00')} null bytes")

# Write back
with open('olympiads.py', 'wb') as f:
    f.write(clean)

print("Written back successfully")

# Verify the file is valid Python
with open('olympiads.py', 'r', encoding='utf-8') as f:
    text = f.read()

try:
    code = compile(text, 'olympiads.py', 'exec')
    print("COMPILE: OK - file is valid Python")
except SyntaxError as e:
    print(f"COMPILE ERROR: {e}")
    # Find the problematic line
    if hasattr(e, 'lineno'):
        lines = text.split('\n')
        if e.lineno <= len(lines):
            line = lines[e.lineno - 1]
            print(f"Line {e.lineno}: {line[:200]}")
    sys.exit(1)

# Now test exec
try:
    exec(text)
    print("EXEC: OK")
    # Count generated solutions
    count = sum(1 for o in OLYMPIADS_DB for p in o.get('problems', []) if p.get('solution_status') == 'generated')
    print(f"Problems with solution_status='generated': {count}")
except Exception as e:
    print(f"EXEC ERROR: {e}")
    sys.exit(1)
