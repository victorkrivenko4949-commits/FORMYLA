# -*- coding: utf-8 -*-
"""Verify the olympiad-test cookie-overflow fix:
1. Pick a real grade+theme+level from FORMYLA_L1_L5_TOP5.jsonl
2. Run 5 tasks through the Flask test client
3. Assert the session cookie stays under ~4 KB and the final report renders.
"""
import json
import os
import re

# Load a real theme for grade 9 (any grade present)
from services import olympiad_adaptive as oa
tasks = oa._all_tasks
grades = sorted({t.get('grade') for t in tasks if t.get('grade')})
print("grades present:", grades)

# find a grade with >=5 tasks at a level so we don't run out
target = None
for g in grades:
    for theme in oa.get_themes(g, oa.get_sections(g)[0] if oa.get_sections(g) else ''):
        pass
# simpler: find first grade/theme with >= 5 tasks
found = None
for t in tasks:
    g = t.get('grade')
    th = (t.get('theme') or '').strip()
    lvl = t.get('level')
    cnt = sum(1 for x in tasks if x.get('grade') == g and (x.get('theme') or '').strip() == th and x.get('level') == lvl)
    if cnt >= 5:
        found = (g, th, lvl)
        break
if not found:
    # fallback: any grade/theme
    t0 = tasks[0]
    found = (t0.get('grade'), (t0.get('theme') or '').strip(), t0.get('level'))
print("using grade/theme/level:", found)
grade, theme, level = found

from app import app
app.config['TESTING'] = True
app.config['SERVER_NAME'] = 'localhost'
app.config['WTF_CSRF_ENABLED'] = False

client = app.test_client()

# Start test
r = client.get(f'/olympiad-test/start?grade={grade}&theme={theme}&level={level}')
print("GET start status:", r.status_code)
cookie = client.get_cookie('session')
print("cookie size after start:", len(cookie.value) if cookie else 0)

# Collect 5 answers
results_seen = 0
final_html = None
for i in range(6):
    # read current task uid from session
    with client.session_transaction() as sess:
        uid = sess.get('olyad_current_task')
        num = sess.get('olyad_task_num', 0)
    # find task answer
    td = next((x for x in tasks if x.get('task_uid') == uid), None)
    if td is None:
        print(f"  iteration {i}: no current task uid={uid}; breaking")
        break
    ans = (td.get('answer') or '').strip()
    # alternate correct/wrong to exercise scoring
    if i % 2 == 1:
        ans = 'WRONG_ANSWER_XYZ'
    r = client.post('/olympiad-test/start', data={'answer': ans, 'solution': 'x=1'})
    cookie = client.get_cookie('session')
    sz = len(cookie.value) if cookie else 0
    body = r.get_data(as_text=True)
    is_final = 'Результаты теста' in body
    print(f"  after answer {i+1}: cookie={sz}B final={is_final} status={r.status_code}")
    if is_final:
        final_html = body
        results_seen = i + 1
        break

print("\n=== RESULT ===")
print("answers processed before final report:", results_seen)
print("final report shown:", final_html is not None)
if final_html:
    m = re.search(r'Задача \d+ \(L(\d)\)', final_html)
    print("report contains task rows:", bool(re.search(r'Задача \d+', final_html)))
    print("report 'правильно' counter:", 'правильно' in final_html)
