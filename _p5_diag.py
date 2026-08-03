# -*- coding: utf-8 -*-
"""Investigate 500 errors."""
import app as A, traceback

c = A.app.test_client()

# Need session for auth routes
with c.session_transaction() as s:
    s['_user_id'] = '1'

# Test each bad route
for path in ['/prep/coach', '/curator/prep/morning-test', '/curator/prep/progress', '/curator', '/curator/', '/topics']:
    try:
        r = c.get(path, follow_redirects=True)
        print(f"{path:35s} CODE={r.status_code} LEN={len(r.data)}")
        if r.status_code == 500:
            print(f"  TRACEBACK: {r.data.decode('utf-8', errors='replace')[:500]}")
    except Exception as e:
        print(f"{path:35s} EXC: {e}")
        traceback.print_exc()

# Test yandex_login separately (might need special auth)
try:
    r = c.get('/yandex_login', follow_redirects=True)
    print(f"{'/yandex_login':35s} CODE={r.status_code} LEN={len(r.data)}")
except Exception as e:
    print(f"{'/yandex_login':35s} EXC: {e}")
    traceback.print_exc()
