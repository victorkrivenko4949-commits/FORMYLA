#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix KaTeX error in E10: remove \# before \text{raznotsvetnykh reber}

Root cause chain:
  Content: \( \#\text{...} \) -> $ \#\text{...} $ (inline math conversion)
  -> Marked.js strips \ before # (markdown escape) -> KaTeX sees bare # -> ERROR
Fix: remove the \# prefix (semantically just "number of" notation)
"""
import json, os, sys

# Force UTF-8 for stdout (Windows cp1251 compatibility)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

FILES = [
    'secrets_dump.json',
    'data/olympiads/methods_catalog_105.json',
]

# Raw file bytes: two backslashes before hash, two before text (JSON-escaped)
# Python string literal: \\\\#\\\\text{...} = "\\\\#\\\\text{raznotsvetnykh reber}"
OLD_RAW = '\\\\#\\\\text{разноцветных рёбер}'
NEW_RAW = '\\\\text{разноцветных рёбер}'

# Decoded JSON: single backslash before hash, single before text
OLD_DEC = '\\#\\text{разноцветных рёбер}'
NEW_DEC = '\\text{разноцветных рёбер}'

fix_count = 0

for filepath in FILES:
    if not os.path.exists(filepath):
        print(f"[SKIP] {filepath} not found")
        continue

    # === Fix raw bytes ===
    with open(filepath, 'r', encoding='utf-8') as f:
        raw = f.read()

    if OLD_RAW in raw:
        raw = raw.replace(OLD_RAW, NEW_RAW)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(raw)
        print(f"[FIXED RAW] {filepath}")
        fix_count += 1
    else:
        print(f"[OK RAW] {filepath}: already fixed or pattern absent")

    # === Fix decoded JSON ===
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    modified = False
    if isinstance(data, list):
        for i, entry in enumerate(data):
            if isinstance(entry, dict):
                for key in ('content', 'worked_example_md', 'definition_md'):
                    val = entry.get(key, '')
                    if isinstance(val, str) and OLD_DEC in val:
                        entry[key] = val.replace(OLD_DEC, NEW_DEC)
                        print(f"  [FIXED DECODED] entry[{i}] key={key}")
                        modified = True
                        fix_count += 1
    elif isinstance(data, dict):
        for key in ('content', 'worked_example_md', 'definition_md'):
            val = data.get(key, '')
            if isinstance(val, str) and OLD_DEC in val:
                data[key] = val.replace(OLD_DEC, NEW_DEC)
                print(f"  [FIXED DECODED] key={key}")
                modified = True
                fix_count += 1

    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  [SAVED] {filepath} (JSON structure updated)")
    else:
        print(f"  (no decoded changes needed)")

print(f"\n=== Total fixes: {fix_count} ===")
