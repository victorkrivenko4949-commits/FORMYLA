#!/usr/bin/env python3
"""Generate services/daily_pool/json_utils.py"""
import os

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "services", "daily_pool", "json_utils.py")

B1 = chr(123)
B2 = chr(125)

src = f'''# -*- coding: utf-8 -*-
"""JSON parsing with LaTeX backslash fix."""
import json
import re


def parse_json_with_latex(text):
    """Parse JSON containing unescaped LaTeX backslashes."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract JSON object
    m = re.search(r'\\{B1}[\\s\\S]*\\{B2}', text)
    if m:
        text = m.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fix: double all single backslashes not followed by valid JSON escape chars
    # Valid JSON escapes: \\\\ \\" \\/ \\b \\f \\n \\r \\t \\uXXXX
    VALID_ESCAPES = '"\\\\/bfnrtu'
    fixed = re.sub(
        r'\\\\(?![' + VALID_ESCAPES + '])',
        r'\\\\\\\\',
        text
    )
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Last resort: raise with truncated text for debugging
    raise json.JSONDecodeError("Cannot parse JSON after LaTeX fix", text[:200], 0)
'''

with open(path, 'w', encoding='utf-8') as f:
    f.write(src)
print(f"Written: json_utils.py ({len(src)} bytes)")
