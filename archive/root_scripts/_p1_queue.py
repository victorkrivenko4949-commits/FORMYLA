# -*- coding: utf-8 -*-
import time, json, sqlite3
import app as A

c = A.app.test_client()
with c.session_transaction() as s:
    s['_user_id'] = '1'

# Start a job
r = c.post('/figures/generate/start', data={
    'problem_text': 'Triangle ABC, AB=AC, angle B=50, find angle A'
}, follow_redirects=True)

print('START_STATUS:', r.status_code)
try:
    data = json.loads(r.data)
    print('START_DATA keys:', list(data.keys()))
    job_id = data.get('job_id')
    print('JOB_ID:', job_id)
except Exception as e:
    print('PARSE_ERROR:', e, r.data[:300])
    job_id = None

if job_id:
    seen = []
    for i in range(30):
        try:
            rs = c.get('/figures/generate/status/{}'.format(job_id))
            st = json.loads(rs.data).get('status')
            if not seen or seen[-1] != st:
                seen.append(st)
                print('STATUS_CHANGE:', st, 'at poll', i)
            if st in ('done', 'failed'):
                break
        except Exception as ex:
            print('POLL_ERROR:', ex)
        time.sleep(2)
    print('SEQUENCE:', seen)

    conn = sqlite3.connect('instance/formyla.db')
    rows = conn.execute("SELECT id, status, credit_charged FROM figure_build_jobs ORDER BY id DESC LIMIT 3").fetchall()
    print('BUILD_JOBS:', rows)
    conn.close()
