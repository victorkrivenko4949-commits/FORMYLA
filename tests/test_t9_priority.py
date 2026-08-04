# -*- coding: utf-8 -*-
"""
tests/test_t9_priority.py — T9: subscriber priority in figure build queue.

Tests:
  - test_subscriber_first — subscriber (priority=1) jobs processed before
    free (priority=0) jobs.
  - test_queue_position_scope — queue_position and queue_total count only
    the user's own jobs, not another user's.
  - test_queue_status_route — /figures/generate/queue-status returns
    correct JSON.
"""

import json
import pytest
from datetime import datetime, timedelta


# ── Helpers ──────────────────────────────────────────────────────────────

def _process_one_queued_job(app):
    """Pick the first queued job per priority-then-FIFO ordering and
    mark it 'done'.  Returns the FigureBuildJob or None.

    This mirrors the ordering used by _queue_worker_loop() but does not
    call the real reasoner/engine pipeline — it only advances status.
    """
    from models import db, FigureBuildJob

    job = FigureBuildJob.query.filter_by(status='queued').order_by(
        FigureBuildJob.priority.desc(),
        FigureBuildJob.created_at,
    ).first()

    if job is None:
        return None

    job.status = 'done'
    job.svg_path = '<svg></svg>'
    job.updated_at = datetime.utcnow()
    db.session.commit()
    return job


# ── Tests ────────────────────────────────────────────────────────────────

def test_subscriber_first(app, user_subscribed, user_free, five_priority_jobs):
    """Subscriber jobs (priority=1) are dequeued before free (priority=0).

    Creates 3 subscriber + 2 free queued jobs.  Processes all five
    one by one and asserts the first three belong to user_subscribed.
    """
    from models import FigureBuildJob

    # Verify initial state: 5 queued jobs total
    all_queued = FigureBuildJob.query.filter_by(status='queued').count()
    assert all_queued == 5

    processed = []
    for _ in range(5):
        job = _process_one_queued_job(app)
        assert job is not None, f"Expected job {len(processed) + 1} but queue empty"
        processed.append(job)

    # First three must be subscriber jobs
    for i in range(3):
        assert processed[i].user_id == user_subscribed.id, (
            f"Job {i + 1} expected subscriber ({user_subscribed.id}) "
            f"but got user {processed[i].user_id}"
        )
        assert processed[i].priority == 1

    # Last two must be free user jobs
    for i in range(3, 5):
        assert processed[i].user_id == user_free.id, (
            f"Job {i + 1} expected free user ({user_free.id}) "
            f"but got user {processed[i].user_id}"
        )
        assert processed[i].priority == 0

    # No more queued jobs
    remaining = FigureBuildJob.query.filter_by(status='queued').count()
    assert remaining == 0


def test_queue_position_scope(app, user_subscribed, user_free, five_priority_jobs):
    """queue_position and queue_total count only the requesting user's jobs.

    free user has 2 queued jobs — position and total must reflect only those.
    """
    from routes.figures_generator import queue_position, queue_total
    from models import FigureBuildJob

    # Get free user's latest queued job
    free_jobs = FigureBuildJob.query.filter_by(
        user_id=user_free.id, status='queued',
    ).order_by(FigureBuildJob.created_at).all()

    assert len(free_jobs) == 2, f"Expected 2 free jobs, got {len(free_jobs)}"

    # queue_position for free user's first (earliest) job
    pos1 = queue_position(free_jobs[0])
    # queue_total
    total_free = queue_total(user_free.id)

    assert pos1 == 1, f"Expected position 1 for free user's earliest job, got {pos1}"
    assert total_free == 2, f"Expected total 2 for free user, got {total_free}"

    # queue_position for free user's last job
    pos2 = queue_position(free_jobs[1])
    assert pos2 == 2, f"Expected position 2 for free user's latest job, got {pos2}"

    # Subscriber total should be 3 (not 5)
    total_sub = queue_total(user_subscribed.id)
    assert total_sub == 3, f"Expected total 3 for subscriber, got {total_sub}"


def test_queue_status_route(app, user_free, client):
    """GET /figures/generate/queue-status returns JSON with position/total/priority."""
    # Log in as free user
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_free.id)

    # Create 2 free user queued jobs
    from models import db, FigureBuildJob
    from datetime import datetime

    base = datetime.utcnow() - timedelta(minutes=10)
    for i in range(2):
        job = FigureBuildJob(
            user_id=user_free.id,
            problem_text=f'[TEST] queue-status job {i + 1}',
            status='queued',
            model_name='test-model',
            credit_charged=False,
            has_aux=False,
            priority=0,
            created_at=base + timedelta(seconds=i * 10),
            updated_at=base + timedelta(seconds=i * 10),
        )
        db.session.add(job)
    db.session.commit()

    resp = client.get('/figures/generate/queue-status', follow_redirects=True)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    data = json.loads(resp.data.decode('utf-8'))
    keys = sorted(data.keys())
    assert keys == ['position', 'priority', 'total'], f"Keys mismatch: {keys}"
    assert data['position'] >= 1, f"position must be >= 1, got {data['position']}"
    assert data['total'] == 2, f"total must be 2, got {data['total']}"
    assert data['priority'] == 0, f"priority must be 0 for free user, got {data['priority']}"


def test_queue_status_no_jobs(app, user_free, client):
    """Queue status returns zeros when no queued jobs exist."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_free.id)

    resp = client.get('/figures/generate/queue-status', follow_redirects=True)
    assert resp.status_code == 200

    data = json.loads(resp.data.decode('utf-8'))
    assert data == {"position": 0, "total": 0, "priority": 0}, (
        f"Expected zeros, got {data}"
    )
