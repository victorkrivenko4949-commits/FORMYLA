# -*- coding: utf-8 -*-
"""Smoke test for /olympiads/* templates: just GET them and check status codes."""

import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

import app as a

URLS = [
    '/olympiads/courses',
    '/olympiads/vsosh-9-2027',
    '/olympiads/methods',
    '/olympiads/methods/E14',
    '/olympiads/probnik/vsosh-9-2027-topic-1',
    '/olympiads/probnik/vsosh-9-2027-stage-1',
    '/olympiads/task/10',
    '/olympiads/task/12',
    # my-progress requires login; expect 302 redirect.
    '/olympiads/my-progress',
]

with a.app.test_client() as c:
    print()
    for url in URLS:
        r = c.get(url, follow_redirects=False)
        body_preview = ''
        if r.status_code >= 500:
            body_preview = ' | ' + r.data[:300].decode('utf-8', errors='replace').replace('\n', ' ')
        print(f"{r.status_code:4d}  {url}{body_preview}")
