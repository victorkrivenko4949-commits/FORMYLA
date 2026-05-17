# -*- coding: utf-8 -*-
"""Smoke-test: страницы методов каталога теории."""
import sys
import urllib.error
import urllib.request

CODES = ['A2a', 'G1', 'H1']
BASE = 'http://127.0.0.1:5000/olympiads/methods/'

ok = True
for code in CODES:
    url = BASE + code
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode('utf-8', errors='replace')
        status = r.status
        size_kb = round(len(body) / 1024, 1)
        # Признак того, что теория есть: страница длиннее 8 КБ
        # и не содержит шаблонной фразы про placeholder.
        has_theory = (
            size_kb > 8
            and 'Теория этого метода ещё готовится' not in body
            and 'Контент теории появится позже' not in body
        )
        flag = 'OK' if has_theory else 'EMPTY'
        print('{0:>3}  {1}  size={2}KB  theory={3}'.format(
            status, url, size_kb, flag
        ))
        if status != 200 or not has_theory:
            ok = False
    except urllib.error.HTTPError as e:
        print('{0:>3}  {1}  [HTTP error]'.format(e.code, url))
        ok = False
    except Exception as e:
        print('ERR  {0}  -> {1}'.format(url, e))
        ok = False

sys.exit(0 if ok else 1)
