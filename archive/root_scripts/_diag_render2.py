# -*- coding: utf-8 -*-
"""Diagnostic v2: check template file directly + check for cached compiled templates."""
import sys, io, os, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

print("=" * 60)
print("DIAG: Template file on disk")

tmpl_path = os.path.join('templates', 'prep', 'coach.html')
if os.path.exists(tmpl_path):
    size = os.path.getsize(tmpl_path)
    mtime = os.path.getmtime(tmpl_path)
    import datetime
    mtime_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
    print(f"  Path: {tmpl_path}")
    print(f"  Size: {size} bytes")
    print(f"  Modified: {mtime_str}")
    
    with open(tmpl_path, 'rb') as f:
        raw = f.read()
    
    text = raw.decode('utf-8', errors='replace')
    
    checks = [
        ('addMsg function', "function addMsg"),
        ('toggleKeyboard', "function toggleKeyboard"),
        ('kbInsert', "function kbInsert"),
        ('switchKbTab', "function switchKbTab"),
        ('AbortController', "AbortController"),
        ('cache busting', "?_t="),
        ('DOMContentLoaded', "DOMContentLoaded"),
        ('Chart.js CDN', "chart.js@4.4.0"),
        ('Radar chart init', "getElementById('masteryRadar')"),
        ('greeting fetch', "fetch(greetingUrl"),
        ('onboarding_test scenario', "onboarding_test"),
    ]
    
    all_pass = True
    for name, pattern in checks:
        found = pattern.lower() in text.lower()
        status = "[OK]" if found else "[ERROR]"
        if not found:
            all_pass = False
        print(f"  {status} {name}: {'found' if found else 'MISSING!'}")
    
    print()
    if all_pass:
        print("RESULT: ALL CHECKS PASS - template file on disk is correct!")
    else:
        print("RESULT: SOME CHECKS FAILED - template file is INCOMPLETE!")
else:
    print(f"  [ERROR] File NOT FOUND at {tmpl_path}")

# Check for compiled template caches
print()
print("=" * 60)
print("DIAG: Looking for compiled template caches")
pycache_dirs = [
    os.path.join('templates', 'prep', '__pycache__'),
    os.path.join('templates', '__pycache__'),
    os.path.join('__pycache__'),
]

for d in pycache_dirs:
    if os.path.isdir(d):
        files = os.listdir(d)
        coach_caches = [f for f in files if 'coach' in f.lower()]
        if coach_caches:
            print(f"   {d}/")
            for f in coach_caches:
                fpath = os.path.join(d, f)
                fsize = os.path.getsize(fpath)
                fmtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath)).strftime('%Y-%m-%d %H:%M:%S')
                print(f"    {f} ({fsize} bytes, modified {fmtime})")
        else:
            print(f"   {d}/ (no coach-related cache files)")
    else:
        print(f"  [ERROR] {d}/ (not found)")

# Check for .pyc files anywhere related to coach
print()
print("DIAG: Searching for any coach-related .pyc files")
for root, dirs, files in os.walk('.'):
    for f in files:
        if 'coach' in f.lower() and f.endswith('.pyc'):
            fpath = os.path.join(root, f)
            fsize = os.path.getsize(fpath)
            fmtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath)).strftime('%Y-%m-%d %H:%M:%S')
            print(f"   {fpath} ({fsize} bytes, modified {fmtime})")

print()
print("=" * 60)
print("DIAG: Checking base.html for potential JS blocking issues")

base_path = os.path.join('templates', 'base.html')
if os.path.exists(base_path):
    with open(base_path, 'rb') as f:
        base_raw = f.read()
    base_text = base_raw.decode('utf-8', errors='replace')
    
    # Find all <script> tags
    import re
    script_tags = re.findall(r'<script[^>]*>.*?</script>', base_text, re.DOTALL)
    print(f"  Found {len(script_tags)} <script> blocks in base.html")
    
    # Check for defer
    defer_count = base_text.count('defer')
    print(f"  'defer' occurrences: {defer_count}")
    
    # Check if extra_js is present
    if '{% block extra_js %}' in base_text:
        # Find what comes before extra_js
        idx = base_text.index('{% block extra_js %}')
        before = base_text[max(0,idx-500):idx]
        print(f"  Content before extra_js (last 500 chars):")
        print(f"  ...{before[-200:]}")
    else:
        print("  [ERROR] 'extra_js' block NOT FOUND in base.html!")
    
    # Check for service worker registration
    if 'sw.js' in base_text:
        print("  [OK] Service Worker (sw.js) registered in base.html")
    
    # Check for wb_pip.js
    if 'wb_pip.js' in base_text:
        idx = base_text.index('wb_pip.js')
        context = base_text[max(0,idx-100):idx+200]
        print(f"  wb_pip.js context: ...{context}...")
else:
    print(f"  [ERROR] base.html not found")
