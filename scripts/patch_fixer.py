#!/usr/bin/env python3
"""Patch fix_latex_adaptive.py to fix line 95"""
target = "scripts/fix_latex_adaptive.py"
with open(target, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Line 95 (index 94) has two statements on one line separated by literal \n
# and also has \\\\(sqrt|frac) instead of \\(sqrt|frac)
bad = lines[94]
print("BEFORE:", repr(bad))

# Replace the bad line with two correct lines
line1 = "    pat = re.compile(r'" + chr(92)*2 + "(sqrt|frac)')" + chr(10)
line2 = "    matches = list(pat.finditer(text))" + chr(10)
lines[94] = line1
lines.insert(95, line2)

print("AFTER 94:", repr(lines[94]))
print("AFTER 95:", repr(lines[95]))

with open(target, "w", encoding="utf-8") as f:
    f.writelines(lines)
print("Patched successfully")
