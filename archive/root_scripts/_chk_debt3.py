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
        out.write('has toggle btn: %s\n' % ('Открыть долг' in html))
        out.write('has toggleDebt fn: %s\n' % ('toggleDebt' in html))
        out.write('has openDebtTask fn: %s\n' % ('openDebtTask' in html))
        out.write('onclick openDebtTask count: %d\n' % html.count('openDebtTask('))
        # check rendered onclick has numeric id
        m = re.search(r'openDebtTask\((\d+)\)', html)
        out.write('sample onclick id: %s\n' % (m.group(1) if m else 'NO'))
except Exception as e:
    out.write('ERROR %r\n' % e)

open('_chk_debt3.txt', 'w', encoding='utf-8').write(out.getvalue())
print('done')
