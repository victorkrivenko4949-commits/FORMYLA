# -*- coding: utf-8 -*-
"""K1: Test no double charge on race condition.

Two concurrent calls to _charge_credit on the same job must result in
exactly one credit charged, not two.  The atomic UPDATE ... WHERE
credit_charged = 0 guarantees this.

Each thread pushes its own app_context() so that db.session is available.
"""

import threading
import queue
import time


def test_no_double_charge_race(app, test_user):
    """Simulate two parallel charge attempts on the same job.

    Exactly one succeeds, the other returns 'already charged'.
    """
    from models import db, FigureBuildJob
    from datetime import datetime

    test_user.figure_credits = 5
    db.session.commit()

    job = FigureBuildJob(
        user_id=test_user.id,
        problem_text='[TEST K1] race condition test',
        status='queued',
        model_name='test-model',
        credit_charged=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(job)
    db.session.commit()

    results = queue.Queue()
    barrier = threading.Barrier(2, timeout=10)  # ensure both threads start together

    def attempt_charge(app_obj, job_id, result_queue, sync_barrier):
        with app_obj.app_context():
            from routes.figures_generator import _charge_credit
            try:
                # Wait at barrier so both threads hit _charge_credit roughly
                # simultaneously — maximises the chance of racing on the
                # atomic UPDATE.
                sync_barrier.wait()
                # tiny sleep to let both arrive at DB level
                time.sleep(0.05)
                ok, msg = _charge_credit(job_id)
                result_queue.put((ok, msg))
            except Exception as e:
                result_queue.put((False, str(e)))

    t1 = threading.Thread(target=attempt_charge, args=(app, job.id, results, barrier))
    t2 = threading.Thread(target=attempt_charge, args=(app, job.id, results, barrier))

    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    outcomes = []
    while not results.empty():
        outcomes.append(results.get())

    # Exactly one should be a real charge (ok=True, msg="")
    real_charge_count = sum(1 for ok, msg in outcomes if ok and msg == "")
    already_count = sum(1 for _, msg in outcomes if msg == 'already charged')

    assert real_charge_count == 1, (
        f"Expected exactly 1 real charge, got {real_charge_count}. "
        f"All outcomes: {outcomes}"
    )
    assert already_count == 1, (
        f"Expected 1 'already charged', got {already_count}. "
        f"All outcomes: {outcomes}"
    )

    # Verify final state in DB
    from models import User, FigureCreditTransaction
    user = User.query.get(test_user.id)
    assert user.figure_credits == 4, (
        f"Expected credits=4 (5-1), got {user.figure_credits}"
    )

    spend_txns = FigureCreditTransaction.query.filter_by(
        user_id=test_user.id,
        reason='spend_ch5',
    ).count()
    assert spend_txns == 1, (
        f"Expected exactly 1 spend transaction, got {spend_txns}"
    )
