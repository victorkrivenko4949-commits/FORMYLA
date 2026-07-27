# -*- coding: utf-8 -*-
"""Diagnostic: render coach template directly and check for expected JS content."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app import app
import jinja2

# Check template auto reload setting
print("=" * 60)
print("DIAG: Flask template config")
print(f"  app.debug = {app.debug}")
print(f"  app.jinja_env.auto_reload = {app.jinja_env.auto_reload}")
print(f"  TEMPLATES_AUTO_RELOAD = {app.config.get('TEMPLATES_AUTO_RELOAD', 'NOT SET')}")
print()

# Check if there are cached templates
print("DIAG: Jinja2 environment cache")
cache = app.jinja_env.cache
if hasattr(cache, 'cache'):
    print(f"  Cache type: {type(cache).__name__}")
    print(f"  Cache size: {cache.cache.get_size() if hasattr(cache.cache, 'get_size') else 'N/A'}")
    print(f"  Cache items: {list(cache.cache.keys()) if hasattr(cache.cache, 'keys') else 'N/A'}")
elif hasattr(cache, '__dict__'):
    print(f"  Cache attrs: {dir(cache)}")
else:
    print(f"  Cache: {cache}")
print()

# Load the coach template directly from filesystem
print("DIAG: Loading coach template directly")
from jinja2 import FileSystemLoader
loader = FileSystemLoader('templates')
source = loader.get_source(app.jinja_env, 'prep/coach.html')
print(f"  Template source loaded: {len(source[0])} bytes")
print()

# Check for key strings in the source
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
    found = pattern.lower() in source[0].lower()
    status = "✅" if found else "❌"
    if not found:
        all_pass = False
    print(f"  {status} {name}: {'found' if found else 'MISSING!'}")

print()
if all_pass:
    print("RESULT: ALL CHECKS PASS - template file on disk is correct!")
else:
    print("RESULT: SOME CHECKS FAILED - template file is INCOMPLETE!")

# Now render the template with a mock context to check for Jinja errors
print()
print("=" * 60)
print("DIAG: Attempting to render template (may fail due to missing context)")
print("(This is expected to need a request context)")
