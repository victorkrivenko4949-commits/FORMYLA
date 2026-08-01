# -*- coding: utf-8 -*-
"""Final route check — print all needed status codes."""
import sys, io, os
os.environ['FLASK_ENV'] = 'test'
sys.path.insert(0, '.')
_old = sys.stdout
sys.stdout = io.StringIO()
from app import app; app.config['TESTING'] = True; app.config['SERVER_NAME'] = 'localhost'
sys.stdout = _old
c = app.test_client()
with c.session_transaction() as s: s['_user_id'] = '1'; s['_fresh'] = True
lines = []
for url in ['/daily_tasks', '/daily_tasks/', '/prep/coach', '/prep/onboarding']:
    r = c.get(url, follow_redirects=False)
    lines.append(f'{url} -> {r.status_code}')
with open('_final_routes.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print('Done')
for line in lines:
    print(line)
