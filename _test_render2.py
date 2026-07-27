# -*- coding: utf-8 -*-
"""Render coach template via Flask test client - v2 without stdout wrapping."""
import os, hashlib, sys

# Set test environment before importing app
os.environ['FLASK_RELOAD'] = '0'

# Don't touch sys.stdout - let app.py use it as-is

# Now check the template source directly from disk
tmpl_path = os.path.join('templates', 'prep', 'coach.html')
with open(tmpl_path, 'rb') as f:
    source_bytes = f.read()

source = source_bytes.decode('utf-8', errors='replace')
source_md5 = hashlib.md5(source_bytes).hexdigest()

print(f"Template file: {tmpl_path}")
print(f"Size: {len(source_bytes)} bytes")
print(f"MD5: {source_md5}")
print()

checks = [
    ('addMsg function', 'function addMsg'),
    ('toggleKeyboard', 'function toggleKeyboard'),
    ('kbInsert', 'function kbInsert'),
    ('switchKbTab', 'function switchKbTab'),
    ('AbortController', 'AbortController'),
    ('cache busting', '?_t='),
    ('DOMContentLoaded', 'DOMContentLoaded'),
    ('Chart.js CDN', 'chart.js@4.4.0'),
    ('Radar chart init', "getElementById('masteryRadar')"),
    ('greeting fetch', 'fetch(greetingUrl'),
    ('onboarding_test', 'onboarding_test'),
    ('console.log coach', "console.log('[coach]"),
]

all_pass = True
for name, pattern in checks:
    found = pattern.lower() in source.lower()
    status = "✅" if found else "❌"
    if not found:
        all_pass = False
    print(f"  {status} {name}: {'found' if found else 'MISSING!'}")

print()
print(f"Overall: {'✅ ALL PASS' if all_pass else '❌ SOME FAILED'}")

# Now try importing Flask to test template loading from Jinja
print()
print("=" * 60)
print("Attempting Flask import for Jinja template check...")
try:
    from jinja2 import FileSystemLoader
    loader = FileSystemLoader('templates')
    
    # We can load the source without Flask
    from jinja2 import Environment
    env = Environment(loader=loader)
    tmpl = env.get_template('prep/coach.html')
    tmpl_source = env.loader.get_source(env, 'prep/coach.html')
    print(f"  Jinja loaded template: {len(tmpl_source[0])} bytes")
    
    jm = hashlib.md5(tmpl_source[0].encode('utf-8')).hexdigest()
    print(f"  Jinja source MD5: {jm}")
    print(f"  Jinja == Disk: {jm == source_md5}")
    
    if jm != source_md5:
        print("  ❌ MISMATCH! Jinja is loading different content than disk!")
    else:
        print("  ✅ Jinja loads EXACTLY the same content as disk")
    
except Exception as e:
    print(f"  Error: {type(e).__name__}: {e}")
