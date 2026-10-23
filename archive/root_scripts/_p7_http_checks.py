"""P7 HTTP acceptance checks — all in one app startup."""
import app as A
c = A.app.test_client()

# Auth
with c.session_transaction() as s:
    s['_user_id'] = '1'

print("=== CHECK 1 (D1): daily/probe answer routes ===")
r = c.post('/daily_tasks/1/submit', data={'answer': 'x'}, follow_redirects=True)
print('DAILY_STATUS', r.status_code)
r2 = c.post('/prep/probe/submit', data={'task_id': 1, 'answer': 'x'}, follow_redirects=True)
print('PROBE_STATUS', r2.status_code)
text = open('templates/daily_task.html', encoding='utf-8').read()
print('HAS_SOFT_TEXT', 'Покажи решение, если хочешь разбор' in text)
print('HAS_FORBIDDEN', 'решение делать не надо' in text)

print("\n=== CHECK 8 (L1): route statuses ===")
print('FIGURES', c.get('/figures', follow_redirects=True).status_code)
print('DRAWING', c.get('/drawing', follow_redirects=True).status_code)
print('API_DRAWING', c.post('/api/drawing/generate', follow_redirects=True).status_code)

print("\n=== CHECK 10 (L1): tables and credits ===")
import sqlite3
conn = sqlite3.connect('instance/formyla.db')
for t in ['figure_credit_transactions', 'figure_generations']:
    r = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchall()
    print(t, bool(r) or 'NOT FOUND')
conn.close()
print('HAS_FIGURE_CREDITS', hasattr(A.User, 'figure_credits'))

print("\n=== CHECK 12 (K1): rate limit + char limit ===")
codes = []
for i in range(11):
    r = c.post('/figures/generate/start', data={'problem_text': f'task {i}'}, follow_redirects=True)
    codes.append(r.status_code)
print('CODES', codes)
r_long = c.post('/figures/generate/start', data={'problem_text': 'x' * 4001}, follow_redirects=True)
print('LONG_STATUS', r_long.status_code)

print("\n=== CHECK 13 (K1): stub mark ===")
stub_text = open('services/yookassa_stub.py', encoding='utf-8').read()
print('HAS_STUB_MARK', 'stub' in stub_text.lower())

print("\n=== ALL HTTP CHECKS COMPLETE ===")
