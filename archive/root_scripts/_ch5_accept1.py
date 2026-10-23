import app as A
c = A.app.test_client()
with c.session_transaction() as s:
    s['_user_id'] = '1'

r1 = c.get('/figures', follow_redirects=True)
print('FIGURES STATUS', r1.status_code)
print('FIGURES LEN', len(r1.data))

r2 = c.get('/drawing', follow_redirects=True)
print('DRAWING STATUS', r2.status_code)
print('DRAWING LEN', len(r2.data))

r3 = c.get('/figures/generate', follow_redirects=True)
print('GENERATE STATUS', r3.status_code)
print('GENERATE LEN', len(r3.data))
