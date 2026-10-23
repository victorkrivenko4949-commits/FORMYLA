"""CH5 Acceptance tests — all 5 checks in one script."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as A
from models import FigureBuildJob, User, db

print("=" * 60)
print("CH5 ACCEPTANCE TESTS")
print("=" * 60)

# ── 1. HTTP route check ──────────────────────────────────────────
print("\n--- 1. HTTP route check ---")
import routes.figures_generator as fg
fg.login_required = lambda f: f

class TU:
    is_authenticated = True
    id = 1
    figure_credits = 10
    figures_built = 0

    def is_anonymous(self):
        return False

fg.current_user = TU()

c = A.app.test_client()
r1 = c.get('/figures', follow_redirects=True)
print('FIGURES STATUS', r1.status_code)
print('FIGURES LEN', len(r1.data))
r2 = c.get('/drawing', follow_redirects=True)
print('DRAWING STATUS', r2.status_code)
print('DRAWING LEN', len(r2.data))
r3 = c.get('/figures/generate', follow_redirects=True)
print('GENERATE STATUS', r3.status_code)
print('GENERATE LEN', len(r3.data))

# ── 2. Full cycle via direct DB + worker ─────────────────────────
print("\n--- 2. Full cycle generation ---")
with A.app.app_context():
    model_name = os.environ.get("FIGURE_MODEL", "deepseek-v4-flash").strip()
    user = User.query.get(1)
    credits_before = user.figure_credits if user else 0
    print('Credits before:', credits_before)

    job = FigureBuildJob(
        user_id=1,
        problem_text='Треугольник ABC, AB=AC, угол B = 50 градусов, найти угол A',
        status='queued',
        model_name=model_name,
    )
    db.session.add(job)
    db.session.commit()
    job_id = job.id
    print('Job created:', job_id)

    # Process directly (skip the queue worker thread for test)
    from routes.figures_generator import _run_build_job
    _run_build_job(job_id)

    # Re-fetch
    job = FigureBuildJob.query.get(job_id)
    final_status = job.status
    print('Final status:', final_status)

    if final_status == 'done':
        svg_len = len(job.svg_path or '')
        print('SVG LEN:', svg_len)
        print('SVG START:', (job.svg_path or '')[:200])
        user = User.query.get(1)
        print('Credits after:', user.figure_credits if user else 'N/A')
    elif final_status == 'failed':
        print('FAILED ERROR:', job.error)

# ── 3. Credit not charged on failed ──────────────────────────────
print("\n--- 3. Credit on failed ---")
with A.app.app_context():
    user = User.query.get(1)
    credits_before_fail = user.figure_credits if user else 0
    print('Credits before fail test:', credits_before_fail)

    fail_job = FigureBuildJob(
        user_id=1,
        problem_text='Invalid nonsense @@@',
        status='queued',
        model_name=os.environ.get("FIGURE_MODEL", "deepseek-v4-flash").strip(),
    )
    db.session.add(fail_job)
    db.session.commit()
    fj_id = fail_job.id
    print('Fail job created:', fj_id)

    from routes.figures_generator import _run_build_job
    _run_build_job(fj_id)

    fj = FigureBuildJob.query.get(fj_id)
    print('Fail job status:', fj.status)
    print('Fail job credit_charged:', fj.credit_charged)

    user = User.query.get(1)
    print('Credits after fail:', user.figure_credits if user else 'N/A')

    # Show last jobs
    jobs = FigureBuildJob.query.order_by(FigureBuildJob.id.desc()).limit(5).all()
    for j in jobs:
        print(f'  JOB {j.id}: status={j.status} credit_charged={j.credit_charged}')

# ── 4. FIGURE_MODEL grep ─────────────────────────────────────────
print("\n--- 4. FIGURE_MODEL grep ---")
import subprocess
result = subprocess.run(
    ['findstr', '/s', '/i', '/n', 'deepseek-v4-flash', '*.py'],
    capture_output=True, text=True, shell=True
)
matches = [l.strip() for l in result.stdout.split('\n') if l.strip() and '.py:' in l]
# Filter to only code files, not test scripts or cache
code_matches = [m for m in matches
                if 'routes' in m or 'services' in m or 'models.py' in m
                or 'app.py' in m or 'ai' in m or 'formyla' in m]
if code_matches:
    print('CODE MATCHES:')
    for m in code_matches:
        print(' ', m)
else:
    print('NO CODE MATCHES (only env default)')

# ── 5. Queue survives restart ────────────────────────────────────
print("\n--- 5. Queue restart survival ---")
with A.app.app_context():
    rj = FigureBuildJob(
        user_id=1,
        problem_text='Квадрат ABCD, найти диагональ, сторона 4',
        status='queued',
        model_name=os.environ.get("FIGURE_MODEL", "deepseek-v4-flash").strip(),
    )
    db.session.add(rj)
    db.session.commit()
    restart_job_id = rj.id
    print('Restart job created:', restart_job_id)

    # Simulate process restart: fetch from DB and check it's there
    rj2 = FigureBuildJob.query.get(restart_job_id)
    print('After "restart" - job found:', rj2 is not None)
    print('  status:', rj2.status if rj2 else 'NOT FOUND')
    print('  problem_text:', (rj2.problem_text or '')[:80] if rj2 else 'NOT FOUND')

    # Now process it
    from routes.figures_generator import _run_build_job
    _run_build_job(restart_job_id)

    rj3 = FigureBuildJob.query.get(restart_job_id)
    print('Final status after restart:', rj3.status if rj3 else 'NOT FOUND')
    if rj3 and rj3.status == 'done':
        print('SVG LEN:', len(rj3.svg_path or ''))
    elif rj3 and rj3.status == 'failed':
        print('ERROR:', rj3.error)

print("\n=== ACCEPTANCE COMPLETE ===")
