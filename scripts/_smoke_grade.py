# -*- coding: utf-8 -*-
"""Smoke-test для /grade-5 и /grade-6."""

from __future__ import annotations

import sys
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

BASE = 'http://127.0.0.1:5000'

URLS = [
    '/grade-5',
    '/grade-5/natural_numbers',
    '/grade-5/fractions_decimals_percent',
    '/grade-5/geometry_measurement',
    '/grade-5/combinatorics_school',
    '/grade-5/logic_olympiad_intro',
    '/grade-5/natural_numbers?level=1',
    '/grade-5/natural_numbers?level=3',
    '/grade-6',
    '/grade-6/divisibility',
    '/grade-6/fractions_ratio_percent',
    '/grade-6/integers_coordinates',
    '/grade-6/geometry_6',
    '/grade-6/olympiad_logic_combinatorics',
    '/grade-task/1',
    '/grade-task/500',
    '/grade-task/1500',
]


def check(url):
    req = Request(BASE + url, headers={'User-Agent': 'smoke/1.0'})
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.status, len(resp.read())
    except HTTPError as e:
        return e.code, 0
    except URLError as e:
        print(f'   URLError: {e}')
        return -1, 0


def main():
    failures = 0
    print('Smoke-test against ' + BASE)
    print()
    print('STATUS    BYTES  URL')
    print('-' * 70)
    for url in URLS:
        status, size = check(url)
        flag = 'OK ' if status == 200 else 'FAIL'
        print(str(status).rjust(6) + '  ' + str(size).rjust(8) + '  ' + url + '   ' + flag)
        if status != 200:
            failures += 1
    print()
    if failures:
        print('FAIL  ' + str(failures) + ' URL(s) did not return 200')
        return 1
    print('OK  all URLs returned 200')
    return 0


if __name__ == '__main__':
    sys.exit(main())