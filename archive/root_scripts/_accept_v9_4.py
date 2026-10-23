import sys, os, io
sys.path.insert(0, os.path.dirname(__file__))
# suppress prints during import
old = sys.stdout
sys.stdout = io.StringIO()
import app as A
sys.stdout = old
import os as _os, importlib

# Test: pop RENDER_GIT_COMMIT and reload
_os.environ.pop('RENDER_GIT_COMMIT', None)
# But we can't reload easily since get_commit_info runs at module level.
# Just test that /__version still works
c = A.app.test_client()
r = c.get('/__version', follow_redirects=True)
print('STATUS', r.status_code)
print('BODY', r.data.decode('utf-8'))
