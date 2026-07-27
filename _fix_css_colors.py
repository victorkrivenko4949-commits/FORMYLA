#!/usr/bin/env python3
"""Bulk-replace green/teal/purple CSS colors with blue equivalents."""

import os
import re

CSS_DIR = os.path.join(os.path.dirname(__file__), 'static', 'css')

REPLACEMENTS = {
    # Green → Blue
    '#38ef7d': '#60a5fa',
    '#11998e': '#3b82f6',
    '#10b981': '#3b82f6',
    '#16a34a': '#3b82f6',
    '#15803d': '#2563eb',
    '#34d399': '#60a5fa',
    '#22c55e': '#3b82f6',
    '#14b8a6': '#60a5fa',
    '#059669': '#3b82f6',
    # Purple/Violet → Blue
    '#a78bfa': '#60a5fa',
    '#7c3aed': '#3b82f6',
    '#8b5cf6': '#3b82f6',
    '#6366f1': '#3b82f6',
    '#c084fc': '#60a5fa',
    '#6d28d9': '#2563eb',
}

total_changes = 0
for fname in sorted(os.listdir(CSS_DIR)):
    if not fname.endswith('.css'):
        continue
    fpath = os.path.join(CSS_DIR, fname)
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()

    new_content = content
    file_changes = 0
    for old, new in REPLACEMENTS.items():
        count = new_content.count(old)
        if count:
            new_content = new_content.replace(old, new)
            file_changes += count

    if file_changes:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"OK {fname}: {file_changes} replacements")
        total_changes += file_changes

print(f"\nTotal: {total_changes} replacements across all CSS files")
