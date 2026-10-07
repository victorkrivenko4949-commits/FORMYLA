# -*- coding: utf-8 -*-
"""Verify the all_sections ("срез") diagnostic path: 5 tasks, then final report."""
import re
from services import olympiad_adaptive as oa
tasks = oa._all_tasks

# pick a grade with >=5 tasks across sections
grade = None
for g in sorted({t.get('grade') for t in tasks if t.get('grade')}):
    if sum(1 for t in tasks if t.get('grade') == g) >= 5:
        grade = g
        break
print("grade:", grade)

from app import app
app.config['TESTING'] = True
app.config['SERVER_NAME'] = 'localhost'
app.config['WTF_CSRF_ENABLED'] = False
client = app.test_client()

# set scope=all_sections, length=5
r = client.get(f'/olympiad-test?length=5&level_hint=2&scope=all_sections')
print("select class status:", r.status_code)
r = client.get(f'/olympiad-test/start?grade={grade}')
print("start status:", r.status_code)
cookie = client.get_cookie('session')
print("cookie after start:", len(cookie.value) if cookie else 0)

final_html = None
for i in range(6):
    with client.session_transaction() as sess:
        uid = sess.get('olyad_current_task')
    td = next((x for x in tasks if x.get('task_uid') == uid), None)
    if td is None:
        print(f"  iter {i}: no uid={uid}")
        break
    ans = (td.get('answer') or '').strip()
    if i % 2 == 1:
        ans = 'WRONG_XYZ'
    r = client.post('/olympiad-test/start', data={'answer': ans, 'solution': ''})
    cookie = client.get_cookie('session')
    sz = len(cookie.value) if cookie else 0
    body = r.get_data(as_text=True)
    is_final = 'Результаты теста' in body
    print(f"  after answer {i+1}: cookie={sz}B final={is_final}")
    if is_final:
        final_html = body
        break

print("\n=== ALL_SECTIONS RESULT ===")
print("final report shown:", final_html is not None)
if final_html:
    print("task rows:", len(re.findall(r'Задача \d+ \(L\d\)', final_html)))
