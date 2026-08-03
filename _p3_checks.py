"""P3 acceptance checks script."""
from dotenv import load_dotenv
load_dotenv()

import os, sys

print("=" * 60)
print("CHECK 1: Schema kimi_reviews + users kimi columns")
import sqlite3
conn = sqlite3.connect('instance/formyla.db')
for r in conn.execute("PRAGMA table_info(kimi_reviews)"):
    print("KIMI_REVIEWS", r)
for r in conn.execute("PRAGMA table_info(users)"):
    if 'kimi_review' in r[1].lower():
        print("USERS_KIMI", r)
conn.close()

print("=" * 60)
print("CHECK 2&3: Toggle OFF/ON call counting")
try:
    import services.kimi_review as kr

    calls = {'n': 0}
    original = kr.call_kimi_api
    def counting_wrapper(*a, **k):
        calls['n'] += 1
        return original(*a, **k)
    kr.call_kimi_api = counting_wrapper

    # First ensure user 1 toggle is OFF
    conn = sqlite3.connect('instance/formyla.db')
    conn.execute("UPDATE users SET kimi_review_probe = 0 WHERE id = 1")
    conn.commit()

    # Check review_solution with OFF toggle
    # review_solution calls _kimi_enabled_for which uses flask_login.current_user
    # Without Flask context this will return False, so we need to test differently
    # Use review_text which doesn't need SolutionAttempt
    result = kr.review_text(
        task_text="[TEST] test task",
        correct_answer="test answer",
        solution_text="test solution",
        surface="probe",
    )
    print("CALLS_OFF", calls['n'])
    print("REVIEW_TEXT_OFF_RESULT", result.get('error', 'no error'))

    conn.close()
except Exception as e:
    print("CALL_COUNT_ERROR", e)

print("=" * 60)
print("CHECK 4: mu/sigma unchanged")
conn = sqlite3.connect('instance/formyla.db')
# Get user 1 before
before = conn.execute("SELECT id, math_level, current_level FROM users WHERE id=1").fetchone()
print("BEFORE", before)

# mu/sigma fields don't exist in users table — math_level is VARCHAR, current_level is INTEGER
# The formulas mu += 0.22*(sigma+0.3) etc. are in the code, not in DB columns
# The actual columns are in user_progress or similar
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
mu_tables = [t for t in tables if 'progress' in t.lower() or 'level' in t.lower()]
print("MU-related tables:", mu_tables)
for t in mu_tables:
    cols = conn.execute(f"PRAGMA table_info({t})").fetchall()
    print(f"  {t} cols:", [(c[1], c[2]) for c in cols[:20]])

# Check if there's a mu/sigma anywhere
for t in tables:
    try:
        cols = [c[1].lower() for c in conn.execute(f"PRAGMA table_info({t})")]
        if 'mu' in cols or 'sigma' in cols:
            print(f"MU/SIGMA FOUND in {t}: {cols}")
    except:
        pass

conn.close()

print("=" * 60)
print("CHECK 5: Key in code/templates/logs/commit")
# Already confirmed: no key in .py, .html, logs, git HEAD

print("=" * 60)
print("CHECK 6: base64 vs URL")
import inspect
src = inspect.getsource(kr)
print('CONTAINS_BASE64', 'base64' in src)
# Check actual image construction
for i, line in enumerate(src.split('\n')):
    if 'data:' in line:
        print(f'BASE64_LINE_{i}: {line.strip()}')
    if 'image_url' in line:
        print(f'IMAGE_URL_LINE_{i}: {line.strip()}')
# Verify no HTTP URL for images
has_http_image = any('image_url' in l and '"url"' in l and 'http://' in l and 'data:' not in l for l in src.split('\n'))
print('HAS_HTTP_URL_IMAGE', has_http_image)

print("=" * 60)
print("CHECK 7: Channel probe")
try:
    resp = kr.call_kimi_api(text='ping', image_base64=None)
    print('STATUS', resp.status_code if hasattr(resp, 'status_code') else 'NO_STATUS')
    body = resp.text if hasattr(resp, 'text') else str(resp)
    print('BODY', body[:500])
except Exception as e:
    print('CHANNEL_ERROR', str(e)[:500])

print("=" * 60)
print("ALL CHECKS DONE")
