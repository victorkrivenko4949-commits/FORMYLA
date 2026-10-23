#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Diagnose: decode session, inspect page HTML."""
import requests, os, json, sys
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
from flask.sessions import TaggedJSONSerializer

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
SECRET = os.environ.get('SECRET_KEY','')

s = requests.Session()
s.get('http://127.0.0.1:5000/dev_login?uid=1', allow_redirects=True)
s.get('http://127.0.0.1:5000/olympiad-test?length=10&level_hint=2&scope=all_sections')
r = s.get('http://127.0.0.1:5000/olympiad-test/select-section?grade=7', allow_redirects=True)
r = s.get('http://127.0.0.1:5000/olympiad-test/start?grade=7', allow_redirects=True)

cookie = s.cookies.get('session','')
print("SESSION_COOKIE:", cookie[:80]+'...')

ser = URLSafeTimedSerializer(SECRET, salt='cookie-session',
                             signer_kwargs={'key_derivation':'hmac'},
                             serializer=TaggedJSONSerializer())
try:
    data = ser.loads(cookie)
    print("KEYS:", list(data.keys()))
    for k, v in data.items():
        if isinstance(v, str) and len(v) > 100:
            print(f"  {k}: [{len(v)} chars] {v[:100]}...")
        else:
            print(f"  {k}: {repr(v)[:200]}")
    task_uid = data.get('olyad_current_task', '')
    print("TASK_UID:", repr(task_uid))
except Exception as e:
    print(f"DECODE ERROR: {e}")

print("PAGE_LEN:", len(r.text))
print("HAS_RUN:", 'olympiad_test_run' in (r.text or ''))

# Look for statement patterns
import re
txt = r.text
m1 = re.search(r'font-size:\s*1\.05em.*?<div[^>]*>(.*?)</div>', txt.replace('\n',' '), re.DOTALL)
print("MATCH1:", bool(m1))
m2 = re.search(r'1\.05em[^>]*>\s*(.{30,}?)\s*</div>', txt.replace('\n',' '), re.DOTALL)
print("MATCH2:", bool(m2))

# Save page snippet
with open('_diag_page.html', 'w', encoding='utf-8') as f:
    f.write(txt[:5000])
print("WROTE _diag_page.html")
