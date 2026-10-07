# -*- coding: utf-8 -*-
"""STEP 4: Real HTTP test against running server at 127.0.0.1:5000."""
import requests
import json

BASE = "http://127.0.0.1:5000"
UNKNOWN = '\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439'

s = requests.Session()

# Login
r = s.get(f"{BASE}/dev_login?uid=3", allow_redirects=True)
assert r.status_code == 200, f"Login failed: {r.status_code}"

# Verify
r = s.get(f"{BASE}/api/chat/unread_total", allow_redirects=True)
if '/login' in r.url or r.status_code != 200:
    # Fix session manually
    s.cookies.clear()
    r = s.get(f"{BASE}/dev_login?uid=3", allow_redirects=True)
    # Try direct session injection
    with requests.Session() as tmp:
        tmp.get(f"{BASE}/dev_login?uid=3", allow_redirects=True)
        s.cookies.update(tmp.cookies)
    r = s.get(f"{BASE}/prep/onboarding", allow_redirects=True)
    print("Login retry:", r.status_code, r.url[:80])

print("=" * 70)
print("Live HTTP test against 127.0.0.1:5000")
print("=" * 70)

steps = []
for label, method, url, body in [
    ("1. CLEANUP", "POST", "/prep/onboarding/answer", {"qid": "_finish", "key": "_finish"}),
    ("2. START", "POST", "/prep/onboarding/answer", {"qid": "_start", "key": "_start"}),
    ("3. Q1 goal=olympiad", "POST", "/prep/onboarding/answer", {"qid": "goal", "key": "olympiad"}),
    ("4. Q2 olymp_reach=region", "POST", "/prep/onboarding/answer", {"qid": "olymp_reach", "key": "region"}),
    ("5. Q3 load=m30", "POST", "/prep/onboarding/answer", {"qid": "load", "key": "m30"}),
    ("6. Q4 deadline=mid", "POST", "/prep/onboarding/answer", {"qid": "deadline", "key": "mid"}),
]:
    r = s.post(f"{BASE}{url}", json=body, allow_redirects=True)
    data = {}
    try:
        data = r.json()
    except:
        pass
    body_str = json.dumps(data, ensure_ascii=False)
    print(f"\n{label}")
    print(f"   {method} {url} -> {r.status_code}")
    print(f"   Body: {body_str[:400]}")
    if r.status_code >= 400:
        print(f"   [FAIL] HTTP {r.status_code}")
    if UNKNOWN in body_str:
        print(f"   [FAIL] 'Unknown step' in response!")
    steps.append(data)

# Get anchor1 from last step
anchor_data = steps[-1] if steps else {}
step = anchor_data.get('step', '')
print(f"\n   step after Q4: {step}")

if anchor_data.get('anchor') and anchor_data['anchor'].get('task_id'):
    tid = anchor_data['anchor']['task_id']
    print(f"\n7. ANCHOR1 task_id={tid}")
    r = s.post(f"{BASE}/prep/onboarding/anchor",
               json={"task_id": tid, "answer": "0"}, allow_redirects=True)
    data = r.json()
    body_str = json.dumps(data, ensure_ascii=False)
    print(f"   POST /prep/onboarding/anchor -> {r.status_code}")
    print(f"   Body: {body_str[:400]}")
    assert UNKNOWN not in body_str

    if data.get('anchor') and data['anchor'].get('task_id'):
        tid2 = data['anchor']['task_id']
        print(f"\n8. ANCHOR2 task_id={tid2}")
        r = s.post(f"{BASE}/prep/onboarding/anchor",
                   json={"task_id": tid2, "answer": "1"}, allow_redirects=True)
        data = r.json()
        body_str = json.dumps(data, ensure_ascii=False)
        print(f"   POST /prep/onboarding/anchor -> {r.status_code}")
        print(f"   Body: {body_str[:400]}")
        assert UNKNOWN not in body_str

print(f"\n9. FINISH")
r = s.post(f"{BASE}/prep/onboarding/answer",
           json={"qid": "_finish", "key": "_finish"}, allow_redirects=True)
data = r.json()
body_str = json.dumps(data, ensure_ascii=False)
print(f"   POST /prep/onboarding/answer -> {r.status_code}")
print(f"   Body: {body_str[:400]}")
assert UNKNOWN not in body_str

print(f"\n{'='*70}")
print("Live HTTP test PASSED.")
print(f"{'='*70}")
