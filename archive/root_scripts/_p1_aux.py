# -*- coding: utf-8 -*-
import app as A

c = A.app.test_client()
with c.session_transaction() as s:
    s['_user_id'] = '1'

# ---- VITRINA ----
r = c.get('/figures', follow_redirects=True)
print('VITRINE STATUS:', r.status_code)
html = r.data.decode('utf-8')
print('VITRINE_HAS_TOGGLE (aux):', '_aux.svg' in html)

# ---- PROBE ----
r = c.get('/prep/probe', follow_redirects=True)
print('PROBE STATUS:', r.status_code)
html = r.data.decode('utf-8')
print('PROBE_HAS_AUX:', '_aux.svg' in html)

# ---- DAILY ----
r = c.get('/daily-set', follow_redirects=True)
print('DAILY STATUS:', r.status_code)
html = r.data.decode('utf-8')
print('DAILY_HAS_AUX:', '_aux.svg' in html)

# ---- METHOD ----
# Find a real method
import sqlite3
conn = sqlite3.connect('instance/formyla.db')
methods = conn.execute("SELECT code FROM olympiad_theory LIMIT 3").fetchall()
conn.close()

for m in methods:
    code = m[0]
    r = c.get('/olympiad/method/{}'.format(code), follow_redirects=True)
    print('METHOD {} STATUS: {} AUX: {}'.format(code, r.status_code, '_aux.svg' in r.data.decode('utf-8')))
