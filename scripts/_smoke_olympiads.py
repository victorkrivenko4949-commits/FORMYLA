# -*- coding: utf-8 -*-
"""Smoke-check that all olympiad URLs respond 200.

Hits the locally running Flask dev server at 127.0.0.1:5000 and prints
status code + content length for every olympiad route.

Run AFTER `python -m flask run --host=127.0.0.1 --port=5000`.
"""

from __future__ import annotations

import sys
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

BASE = 'http://127.0.0.1:5000'

URLS = [
    '/',
    '/olympiads/courses',
    '/olympiads/vsosh-9-2027',
    '/olympiads/probnik/vsosh-9-2027-topic-5',
    '/olympiads/probnik/vsosh-9-2027-stage-1',
    '/olympiads/methods',
    '/olympiads/methods?grade=9&competition=%D0%92%D1%81%D0%9E%D0%A8',
    '/olympiads/methods?difficulty=3&sort=level',
    '/olympiads/methods?section=E&sort=code',
    '/olympiads/methods/E14',
    '/olympiads/methods/A1',
    '/olympiads/methods/F4a',
]


def check(url):
    req = Request(BASE + url, headers={'User-Agent': 'smoke/1.0'})
    try:
        with urlopen(req, timeout=10) as resp:
            body = resp.read()
            return resp.status, len(body)
    except HTTPError as e:
        body = e.read() if hasattr(e, 'read') else b''
        return e.code, len(body)
    except URLError as e:
        print(f'   URLError: {e}')
        return -1, 0


def main():
    failures = 0
    print(f'Smoke-test against {BASE}\n')
    print(f'{"STATUS":>6}  {"BYTES":>8}  URL')
    print('-' * 70)
    for url in URLS:
        status, size = check(url)
        flag = 'OK ' if status == 200 else 'FAIL'
        print(f'{status:>6}  {size:>8}  {url}   {flag}')
        if status != 200:
            failures += 1
    print()
    if failures:
        print(f'FAIL  {failures} URL(s) did not return 200')
        return 1
    print('OK  all URLs returned 200')
    return 0


if __name__ == '__main__':
    sys.exit(main())
