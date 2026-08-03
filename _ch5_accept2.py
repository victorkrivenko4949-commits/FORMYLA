"""Acceptance test 2: full generation cycle.
Inserts a job directly into figure_build_jobs, then polls status via HTTP.
The daemon queue worker will pick it up and process it.
"""
import json
import time
import os

os.environ['FORMYLA_TEST'] = '1'

import app as A
from models import FigureBuildJob, db as _db

# Create job directly in DB
with A.app.app_context():
    model_name = os.environ.get("FIGURE_MODEL", "deepseek-v4-flash").strip()
    job = FigureBuildJob(
        user_id=1,
        problem_text=(
            'Треугольник ABC, AB=AC, '
            'угол B = 50 градусов, найти угол A'
        ),
        status='queued',
        model_name=model_name,
    )
    _db.session.add(job)
    _db.session.commit()
    job_id = job.id
    print('JOB CREATED:', job_id)

# Monkey-patch login for status polling
import routes.figures_generator as fg
fg.login_required = lambda f: f

class _TU:
    is_authenticated = True
    id = 1
    figure_credits = 10
    figures_built = 0
    def is_anonymous(self):
        return False

fg.current_user = _TU()

c = A.app.test_client()

# Wait for queue worker to process (started automatically on first job)
print('Waiting for queue worker...')
seen = []
for i in range(60):
    time.sleep(2)
    try:
        rs = c.get(f'/figures/generate/status/{job_id}')
        data = json.loads(rs.data)
        st = data.get('status', 'unknown')
        if not seen or seen[-1] != st:
            seen.append(st)
            print(f'STATUS CHANGE [{st}] at poll {i}')
        if st in ('done', 'failed'):
            break
    except Exception as e:
        print(f'Poll {i} error: {e}')

print('SEQUENCE', seen)

if seen and seen[-1] == 'done':
    rs = c.get(f'/figures/generate/status/{job_id}')
    data = json.loads(rs.data)
    svg = data.get('svg', '')
    print('SVG LEN', len(svg))
    print('SVG START', svg[:200])
elif seen and seen[-1] == 'failed':
    with A.app.app_context():
        j = FigureBuildJob.query.get(job_id)
        print('FAILED ERROR:', j.error if j else 'NOT FOUND')
else:
    print('No final status reached. Last seen:', seen[-1] if seen else 'NONE')
    with A.app.app_context():
        j = FigureBuildJob.query.get(job_id)
        if j:
            print('DB STATUS:', j.status)
            print('DB ERROR:', j.error)
