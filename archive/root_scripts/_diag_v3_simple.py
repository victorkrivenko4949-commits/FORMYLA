#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Simple diagnostic - save analysis to JSON."""
import json, os
os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

with open('_last_response_11_v3.txt', 'r', encoding='utf-8') as f:
    raw = f.read()

result = {
    'total_chars': len(raw),
    'open_brackets': raw.count('['),
    'close_brackets': raw.count(']'),
    'starts_with': repr(raw[:200]),
    'ends_with': repr(raw[-200:]),
    'last_char': repr(raw[-1]),
    'first_char': repr(raw[0]),
}

with open('_diag_v3_data.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print("SAVED")
