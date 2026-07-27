# -*- coding: utf-8 -*-
"""Validate JavaScript syntax in coach.html."""
import re, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('templates/prep/coach.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract all <script> blocks
scripts = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
print(f"Found {len(scripts)} script blocks")

for i, js in enumerate(scripts):
    lines = js.split('\n')
    opens = js.count('{')
    closes = js.count('}')
    balanced = 'OK' if opens == closes else 'MISMATCH'
    print(f"  Block {i}: {len(js)} chars, braces: {opens} open / {closes} close [{balanced}]")
    non_empty = [l for l in lines if l.strip()]
    print(f"    Non-empty lines: {len(non_empty)}")
    # Check if key patterns exist
    if 'addMsg' in js:
        print(f"    ✅ Has addMsg()")
    if 'DOMContentLoaded' in js:
        print(f"    ✅ Has DOMContentLoaded")
    if 'toggleKeyboard' in js:
        print(f"    ✅ Has toggleKeyboard()")
    if 'kbInsert' in js:
        print(f"    ✅ Has kbInsert()")
    if 'switchKbTab' in js:
        print(f"    ✅ Has switchKbTab()")

print("\n--- Checking for inline onclick handlers ---")
if 'toggleKeyboard()' in content:
    print("❌ toggleKeyboard() used in onclick but not defined in any script block in coach.html")
if 'kbInsert(' in content:
    print("❌ kbInsert() used in onclick but not defined in any script block in coach.html")
if 'switchKbTab(' in content:
    print("❌ switchKbTab() used in onclick but not defined in any script block in coach.html")

print("\nDone.")
