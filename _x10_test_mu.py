# -*- coding: utf-8 -*-
"""X10 mu/sigma test — Kimi must not affect levels. CLEAN: reads from .env."""
import os
import sqlite3
from dotenv import load_dotenv
load_dotenv()

conn = sqlite3.connect('instance/formyla.db')

# Check if user 1 exists
users = [r for r in conn.execute('SELECT id, math_level, current_level FROM users WHERE id=1')]
if not users:
    print("NO_USER_1 — mu/sigma test SKIPPED (no users in DB)")
    conn.close()
    exit(0)

before = str(users)
open('_recon/x10_before_off.txt', 'w', encoding='utf-8').write(before)

import services.kimi_review as kr

calls = {'n': 0}
original = kr.call_kimi_api
def counting_wrapper(*a, **k):
    calls['n'] += 1
    return original(*a, **k)
kr.call_kimi_api = counting_wrapper

# Test with toggle OFF
try:
    kr.review_solution(attempt_id=1, surface='probe')
except Exception as e:
    print(f"EXPECTED_ERROR_OFF: {type(e).__name__}")

print('CALLS_OFF', calls['n'])

after_off = str([r for r in conn.execute('SELECT id, math_level, current_level FROM users WHERE id=1')])
open('_recon/x10_after_off.txt', 'w', encoding='utf-8').write(after_off)

# Enable toggle and test
conn.execute("UPDATE users SET kimi_review_probe=1 WHERE id=1")
conn.commit()

try:
    kr.review_solution(attempt_id=1, surface='probe')
except Exception as e:
    print(f"EXPECTED_ERROR_ON: {type(e).__name__}")

after_on = str([r for r in conn.execute('SELECT id, math_level, current_level FROM users WHERE id=1')])
open('_recon/x10_after_on.txt', 'w', encoding='utf-8').write(after_on)

print('BEFORE', before)
print('AFTER_OFF', after_off)
print('AFTER_ON', after_on)
conn.close()
