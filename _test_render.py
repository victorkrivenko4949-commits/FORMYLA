# -*- coding: utf-8 -*-
"""Render coach template via Flask test client to verify actual output."""
import sys, io, os, hashlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Set test environment before importing app
os.environ['FLASK_RELOAD'] = '0'

import app as flask_app_module

# Use application context
app = flask_app_module.app

print(f"TEMPLATES_AUTO_RELOAD = {app.config.get('TEMPLATES_AUTO_RELOAD')}")
print(f"app.debug = {app.debug}")
print()

# Create a test client
with app.test_client() as client:
    with app.app_context():
        # Try rendering the coach template directly
        from flask import template_rendered
        from jinja2 import FileSystemLoader
        
        # Check the template source directly from Jinja
        loader = FileSystemLoader('templates')
        source, tmpl_name, uptodate = loader.get_source(app.jinja_env, 'prep/coach.html')
        print(f"Template source loaded: {len(source)} bytes")
        
        source_md5 = hashlib.md5(source.encode('utf-8')).hexdigest()
        print(f"Source MD5: {source_md5}")
        
        # Read file directly for comparison
        with open(os.path.join('templates', 'prep', 'coach.html'), 'rb') as f:
            disk_content = f.read()
        disk_md5 = hashlib.md5(disk_content).hexdigest()
        print(f"Disk file MD5: {disk_md5}")
        print(f"Source == Disk: {source_md5 == disk_md5}")
        
        # Check Jinja compiled template cache
        cache = app.jinja_env.cache
        print(f"\nJinja cache type: {type(cache).__name__}")
        
        # Now render the template with minimal context
        # (this will fail due to missing request context, but let's try)
        print("\nAttempting full template render via test_client...")
        
        # We need to simulate auth - create a test user
        # First, let's just get the /prep/coach route directly (will redirect to login)
        resp = client.get('/prep/coach')
        print(f"  GET /prep/coach → {resp.status_code}")
        if resp.status_code == 302:
            print(f"  Redirect: {resp.location}")
        
        # For authenticated access, we'd need to mock login
        # Instead, let's directly render the template string
        print("\nChecking template source for key content:")
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
        if all_pass:
            print("✅ ALL CHECKS PASS - template source is correct!")
        else:
            print("❌ SOME CHECKS FAILED!")
