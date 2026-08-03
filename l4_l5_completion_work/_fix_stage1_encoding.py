#!/usr/bin/env python
"""Fix Unicode chars in _stage1_gap_map.py that crash on Windows cp1251 console.

Problem: Lines 365 and 367 contain Unicode chars U+2713 (CHECK MARK)
and U+26A0 (WARNING SIGN) that can't be encoded to cp1251.
Also line 1 has BOM from PowerShell corruption.

This script surgically replaces these lines with ASCII-safe equivalents.
"""
import os

path = 'l4_l5_completion_work/_stage1_gap_map.py'

# Read as raw bytes
with open(path, 'rb') as f:
    raw = f.read()

print(f'File size: {len(raw)} bytes')
print(f'First 3 bytes: {raw[:3].hex()}')  # Should be EF BB BF if BOM present

# Check for BOM
has_bom = raw.startswith(b'\xef\xbb\xbf')
print(f'Has UTF-8 BOM: {has_bom}')

# Decode as UTF-8 (skip BOM if present)
offset = 3 if has_bom else 0
content = raw[offset:].decode('utf-8')
lines = content.split('\n')

# Find and fix lines 365 and 367 (0-indexed: 364 and 366)
for i, line in enumerate(lines):
    # Line 365 (idx 364): has [OK] or \u2713 or вњ“ (all variants)
    if 'VERIFIED:' in line and 'sum(needed)' in line:
        old = line
        lines[i] = "    print(f'[OK] VERIFIED: sum(needed) = {total_needed} == 189')"
        print(f'Fixed line {i+1}:')
        print(f'  OLD: {repr(old)}')
        print(f'  NEW: {repr(lines[i])}')
    
    # Line 367 (idx 366): has [!] or \u26A0 or вљ (all variants)
    if 'sum(needed)' in line and '!= 189' in line:
        old = line
        lines[i] = "    print(f'[WARN] sum(needed) = {total_needed} != 189. Explain discrepancy.')"
        print(f'Fixed line {i+1}:')
        print(f'  OLD: {repr(old)}')
        print(f'  NEW: {repr(lines[i])}')

# Rejoin and write back (NO BOM, UTF-8 without BOM for Windows compat)
new_content = '\n'.join(lines)
with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f'\nWritten {len(new_content.encode("utf-8"))} bytes to {path}')
print('Encoding fix complete.')
