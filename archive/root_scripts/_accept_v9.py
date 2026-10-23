import sys, os
sys.path.insert(0, os.path.dirname(__file__))

# Suppress noisy prints during import
import io
old_stdout = sys.stdout
sys.stdout = io.StringIO()
import app as A
sys.stdout = old_stdout

import json

c = A.app.test_client()
rv = c.get('/__version', follow_redirects=True)
commit = json.loads(rv.data)['commit']
short = commit[:8]
r = c.get('/', follow_redirects=True)
html = r.data.decode('utf-8')
print('STATUS', r.status_code)
print('SHORT_HASH', short)
print('FOUND_IN_HTML', short in html)
idx = html.find(short)
if idx != -1:
    print('CONTEXT', html[max(0, idx-80):idx+80])
else:
    print('CONTEXT NOT FOUND')
