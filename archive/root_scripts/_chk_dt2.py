# -*- coding: utf-8 -*-
import os, sys, io, contextlib, re, json

os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.abspath('instance/formyla.db').replace('\\', '/')

res = io.StringIO()

with open('logs/_chk_dt2_out.txt', 'w', encoding='utf-8') as fout:
    with contextlib.redirect_stdout(fout), contextlib.redirect_stderr(fout):
        from app import app
        c = app.test_client()
        with c.session_transaction() as s:
            s['_user_id'] = '1302'
        r = c.get('/daily_tasks', follow_redirects=True)
        res.write('STATUS %s\n' % r.status_code)
        txt = r.data.decode('utf-8', errors='replace')
        # extract embedded JSON init data
        m = re.search(r'<script id="dt-init-data" type="application/json">(.*?)</script>', txt, re.S)
        if m:
            try:
                data = json.loads(m.group(1))
                res.write('status=%s\n' % data.get('status'))
                res.write('items=%d\n' % len(data.get('items') or []))
                res.write('theme_today=%s\n' % data.get('theme_today'))
                if data.get('items'):
                    it = data['items'][0]
                    res.write('first_item_topic=%s\n' % it.get('topic'))
                    res.write('first_item_preview=%s\n' % (it.get('task_text') or it.get('preview') or '')[:120])
            except Exception as e:
                res.write('parse err: %s\n' % e)
        else:
            res.write('no init-data found\n')

open('_chk_dt2.txt', 'w', encoding='utf-8').write(res.getvalue())
print('done')
