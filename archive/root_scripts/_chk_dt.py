# -*- coding: utf-8 -*-
import os, sys, io, contextlib

os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.abspath('instance/formyla.db').replace('\\', '/')

res = io.StringIO()

with open('logs/_dt_stdout.txt', 'w', encoding='utf-8') as fout:
    with contextlib.redirect_stdout(fout), contextlib.redirect_stderr(fout):
        from app import app
        c = app.test_client()
        with c.session_transaction() as s:
            s['_user_id'] = '1302'
        r = c.get('/daily_tasks', follow_redirects=True)
        res.write('STATUS %s\n' % r.status_code)
        txt = r.data.decode('utf-8', errors='replace')
        res.write('len %d\n' % len(txt))
        res.write('no_set: %s\n' % ('Задач пока нет' in txt))
        res.write('blocked: %s\n' % ('утренний срез' in txt and 'Пройти' in txt))
        res.write('dt-hidden empty-state visible?')
        # найти data.status
        import re
        m = re.search(r'data-status="([^"]+)"', txt)
        res.write('data-status=%s\n' % (m.group(1) if m else 'N/A'))
        # ищем DTData / status в JS
        for kw in ['"status"', 'no_set', 'blocked', 'ready']:
            i = txt.find(kw)
            res.write('kw %r idx=%d\n' % (kw, i))

open('_dt.txt', 'w', encoding='utf-8').write(res.getvalue())
print('written')
