# -*- coding: utf-8 -*-
"""Verify Cache-Control: no-store on anonymous HTML responses (after fix).

Bug:  Cloudflare/Render edge cached HTML response from a broken anonymous
      session during deploy 7b018a9; new anonymous visitors kept seeing the
      cached "не найдено" page until cache TTL expired (~4h browser TTL).
Fix:  add Cache-Control: no-store to ALL HTML responses (auth + anon), not
      only is_authenticated.
"""
import os, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DATABASE_URL', f'sqlite:///{ROOT}/instance/formyla.db')

from app import app

HTML_PATHS = ['/', '/welcome', '/about', '/adaptive_test/select_class',
              '/leaderboard', '/login']
STATIC_PATHS = ['/health']  # JSON — must remain cacheable

print("=" * 70)
print("ANONYMOUS HTML RESPONSE CACHE-CONTROL CHECK")
print("=" * 70)

with app.test_client() as c:
    fails = 0
    for p in HTML_PATHS:
        r = c.get(p, follow_redirects=False)
        cc = r.headers.get('Cache-Control', '')
        ct = r.headers.get('Content-Type', '')
        vary = r.headers.get('Vary', '')
        ok = ('no-store' in cc) and ('text/html' in ct)
        mark = 'OK ' if ok else 'FAIL'
        if not ok:
            fails += 1
        print(f"[{mark}] {p:35s} status={r.status_code} CC='{cc}' Vary='{vary}'")

    print()
    print("JSON / API responses (must NOT force no-store unless already set):")
    for p in STATIC_PATHS:
        r = c.get(p, follow_redirects=False)
        cc = r.headers.get('Cache-Control', '')
        ct = r.headers.get('Content-Type', '')
        print(f"[INFO] {p:35s} status={r.status_code} CC='{cc}' CT='{ct}'")

print()
print("=" * 70)
print(f"RESULT: {'ALL PASS' if fails == 0 else f'{fails} FAIL'}")
print("=" * 70)
sys.exit(1 if fails else 0)
