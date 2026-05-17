# -*- coding: utf-8 -*-
"""Smoke-тест нового class-first потока адаптивного теста."""
import sys
import urllib.error
import urllib.request

URLS = [
    '/probniks',
    '/adaptive_test/select_class',
    '/adaptive_test/select_topic?grade=5',
    '/adaptive_test/select_topic?grade=6',
    '/adaptive_test/select_topic?grade=7',
    '/adaptive_test/select_topic?grade=9',
    '/adaptive_test/select_topic?grade=11',
    '/adaptive_test/select_topic?grade=99',          # invalid → redirect
    '/adaptive_test/start_grade?grade=5&domain=natural_numbers',
]

ok = True
for u in URLS:
    full = 'http://127.0.0.1:5000' + u
    try:
        req = urllib.request.Request(full, method='GET')
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f'{r.status:>3}  {u}')
    except urllib.error.HTTPError as e:
        print(f'{e.code:>3}  {u}  [HTTP error]')
        ok = False
    except Exception as e:
        print(f'ERR  {u}  -> {e}')
        ok = False

sys.exit(0 if ok else 1)
