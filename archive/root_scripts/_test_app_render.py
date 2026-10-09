#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test app rendering of olympiad detail page for vsosh 2020 regional grade 10."""
import urllib.request
import urllib.parse
import re
import sys

data = urllib.parse.urlencode({
    'olympiad': 'vsosh',
    'year': '2020',
    'grade': '10',
    'round': 'regional'
}).encode()

req = urllib.request.Request(
    'http://127.0.0.1:5001/olympiads/open',
    data=data,
    method='POST'
)

try:
    resp = urllib.request.urlopen(req, timeout=10)
    html = resp.read().decode('utf-8')

    day1_count = html.count('День 1')
    day2_count = html.count('День 2')
    tasks = re.findall(r'Задача (\d+)</span>', html)

    print(f'HTTP {resp.status}')
    print(f'Content length: {len(html)} bytes')
    print(f'Day 1 header found: {day1_count} times')
    print(f'Day 2 header found: {day2_count} times')
    print(f'Total tasks rendered: {len(tasks)}')
    print(f'Task numbers: {tasks}')
    print()

    if day1_count >= 1 and day2_count >= 1 and len(tasks) == 10:
        print('RENDERING VERIFICATION: PASSED')
        print('  - Both Day 1 and Day 2 headers present')
        print('  - All 10 tasks rendered')
    else:
        print('RENDERING VERIFICATION: FAILED')
        sys.exit(1)
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
