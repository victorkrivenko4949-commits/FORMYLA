#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Diagnose session content and page HTML pattern."""
import requests, os, json
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
from flask.sessions import TaggedJSONSerializer

ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT, '.env'))
SECRET = os.environ.get('SECRET_KEY','')

print("SECRET:", SECRET[:30] + "...")

s = requests.Session()
s.get('http://127.0.0.1:5000/dev_login?uid=1', allow_redirects=True)
s.get('http://127.0.0.1:5000/olympiad-test?length=10&level_hint=2&scope=all_sections')
r = s.get('http://127.0.0.1:5000/olympiad-test/select-section?grade=7', allow_redirects=True)
r = s.get('http://127.0.0.1:5000/olympiad-test/start?grade=7', allow_redirects=True)

cookie = s.cookies.get('session','')
ser = URLSafeTimedSerializer(SECRET, salt='cookie-session',
                             signer_kwargs={'key_derivation':'hmac'},
                             serializer=TaggedJSONSerializer())
data = ser.loads(cookie)
print("SESSION KEYS:", list(data.keys()))

# Look for task-related keys
for k in sorted(data.keys()):
    v = data[k]
    if isinstance(v, str) and len(v) > 100:
        print(f"  {k}: [{len(v)}] {v[:120]}...")
    else:
        print(f"  {k}: {repr(v)[:250]}")

# Get olyad_current_task
task_uid = data.get('olyad_current_task', None)
print("\nolyad_current_task:", repr(task_uid))

# Also check other possible keys
for k in data:
    if 'task' in k.lower() or 'olyad' in k.lower() or 'oly' in k.lower():
        print(f"  TASK-KEY {k}: {repr(data[k])[:200]}")

# Save full page body text
with open('_diag_full.html', 'w', encoding='utf-8') as f:
    f.write(r.text)
print("PAGE_LEN:", len(r.text))

# Look for any "task" or "statement" patterns in HTML
import re
# Search for common task rendering patterns
for pat in ['task-text', 'task_statement', 'problem-card', 'task-body', 'olympiad_task',
            'task_uid', 'taskUid', 'data-task', 'font-size.*1\\.05', 'font-size:1\\.05']:
    matches = list(re.finditer(pat, r.text, re.IGNORECASE))
    print(f"  Pattern '{pat}': {len(matches)} matches")

# Show body content snippet
body_match = re.search(r'<body[^>]*>(.*?)</body>', r.text, re.DOTALL)
if body_match:
    body = body_match.group(1)
    print(f"BODY LEN: {len(body)}")
    # Find first non-script, non-style substantial content
    clean = re.sub(r'<script[^>]*>.*?</script>', '', body, flags=re.DOTALL)
    clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
    clean = re.sub(r'<nav[^>]*>.*?</nav>', '', clean, flags=re.DOTALL)
    clean = re.sub(r'<header[^>]*>.*?</header>', '', clean, flags=re.DOTALL)
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    print(f"CLEAN BODY (first 500): {clean[:500]}")
