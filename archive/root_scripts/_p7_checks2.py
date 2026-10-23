"""P7 remaining acceptance checks."""
import app as A
c = A.app.test_client()

# CHECK 2 (C11): aux access
with c.session_transaction() as s:
    s['_user_id'] = '1'

print("=== CHECK 2 (C11): aux access ===")
# Need a real uid/task_id — check figures routes
r = c.get('/figures/aux/probe/1')
print('AUX_BEFORE', r.status_code)
r2 = c.get('/figures/aux/method/1')
print('METHOD_AUX', r2.status_code)

print("\n=== CHECK 7 (I1): SVG content-type + bg ===")
r = c.get('/figures/svg/A_G5_ALG')
print('FIGURES_SVG_STATUS', r.status_code)
if r.status_code == 200:
    ct = r.headers.get('Content-Type', '')
    print('CONTENT_TYPE', ct, 'HAS_SVG', 'svg' in ct.lower())
    print('HAS_BG', '#070C18' in r.data.decode('utf-8', errors='ignore'))

print("\n=== CHECK 11 (K1): credit charge ===")
with A.app.app_context():
    from models import User, FigureBuildJob
    user = User.query.first()
    if user:
        before = user.figure_credits
        print('USER_CREDITS_BEFORE', before)
        job = FigureBuildJob.query.filter_by(status='queued').first()
        if job:
            job.status = 'done'
            from models import db
            db.session.commit()
            after = User.query.get(user.id).figure_credits
            print('DONE_DELTA', before - after)
            # Reset
            job.status = 'queued'
            db.session.commit()
        else:
            print('NO_QUEUED_JOB')
    else:
        print('NO_USER')

print("\n=== CHECK 15: design tokens in templates ===")
import re
ALLOWED = {'#070C18', '#0E1830', '#121F3C', '#1C2B4F', '#E6EBF7', '#8C9ABC', '#4C7DFF', '#6B95FF', '#3ECF8E', '#E5AC3A', '#E86A62'}
# Templates from 8 blocks:
templates = [
    'templates/daily_task.html',        # D1, D2
    'templates/daily_tasks/daily_tasks_dashboard.html',  # D1, D2, D3
    'templates/prep/probe.html',        # D1, C11
    'templates/olympiad/method_task.html', # C11
    'templates/figures.html',           # I1, L1
    'templates/figures_generate.html',  # K1
    'templates/pricing.html',           # K1
    'templates/payment_stub.html',      # K1
]
import os
for path in templates:
    if os.path.exists(path):
        text = open(path, encoding='utf-8').read()
        hex_colors = set(m.upper() for m in re.findall(r'#[0-9A-Fa-f]{6}', text))
        foreign = hex_colors - ALLOWED
        print(path, 'FOREIGN_HEX', foreign if foreign else 'set()')
    else:
        print(path, 'NOT FOUND')

print("\n=== ALL CHECKS COMPLETE ===")
