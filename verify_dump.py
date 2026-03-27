#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Quick verification script for the generated dump file."""

import os

print("=" * 60)
print("FINAL VERIFICATION - project_code_dump.md")
print("=" * 60)

f = 'project_code_dump.md'
size = os.path.getsize(f)

print(f"\nFile: {f}")
print(f"Size: {size:,} bytes ({size/1024/1024:.2f} MB)")
print(f"Exists: {os.path.exists(f)}")
print(f"Readable: {os.access(f, os.R_OK)}")

with open(f, 'r', encoding='utf-8') as file:
    lines = len(file.readlines())
    
print(f"Total lines: {lines:,}")
print("\n" + "=" * 60)
print("Status: SUCCESS - File is valid and readable")
print("=" * 60)
