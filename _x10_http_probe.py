# -*- coding: utf-8 -*-
"""X10 HTTP probe test — verify Kimi label appears in HTML."""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Must import app before other modules
import app as A

c = A.app.test_client()
with c.session_transaction() as s:
    s['_user_id'] = '1'

r = c.get('/prep/probe/1', follow_redirects=True)
html = r.data.decode('utf-8')
print('STATUS', r.status_code)
print('HAS_LABEL', any(l in html for l in ['ход верный', 'дыра в рассуждении', 'угадал']))
# Print first 1500 chars
print(html[:1500])
