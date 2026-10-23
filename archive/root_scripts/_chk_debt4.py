# -*- coding: utf-8 -*-
import io, sys, re
out = io.StringIO()
try:
    from app import app
    with app.test_client() as client:
        client.get('/dev_login?uid=1302')
        resp = client.get('/daily_tasks', follow_redirects=True)
        html = resp.get_data(as_text=True)
        out.write('status=%d len=%d\n' % (resp.status_code, len(html)))
        out.write('open buttons: %d\n' % html.count('Открыть задачу'))
        out.write('openDebtTask( with id: %d\n' % len(re.findall(r'openDebtTask\(\d+\)', html)))
except Exception as e:
    out.write('ERROR %r\n' % e)

open('_chk_debt4.txt', 'w', encoding='utf-8').write(out.getvalue())
print('done')
