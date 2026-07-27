#!/usr/bin/env python3
"""Fix unterminated string literal on line 25 of olympiads.py."""
import sys

path = "olympiads.py"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

old = lines[24]
print(f"Line 25 BEFORE: {repr(old[:80])}")

# Fix: add closing single quote at end of line (before newline)
if old.rstrip().endswith(".") and not old.rstrip().endswith(".'"):
    lines[24] = old.rstrip() + "'\n"
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"Line 25 AFTER:  {repr(lines[24][:80])}")
    print("FIX APPLIED")
else:
    print("Line 25 seems OK or doesn't match expected pattern")
    print(f"repr: {repr(old)}")
