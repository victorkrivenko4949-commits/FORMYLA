# -*- coding: utf-8 -*-
"""K1: Test credit charging on FigureBuildJob status=done.

Uses F0 fixtures (app, test_user, auth_client).
"""

import json


def test_credit_charged_on_done(app, test_user):
    """When a FigureBuildJob transitions to done, exactly 1 credit is spent.

    Verifies:
      - figure_credits decreases by 1
      - Exactly one FigureCreditTransaction with amount=-1 is created
      - The transaction reason is 'spend_ch5'
    """
    from models import db, FigureBuildJob, FigureCreditTransaction
    from datetime import datetime

    # Setup: give the user 5 credits and create a job
    test_user.figure_credits = 5
    db.session.commit()

    job = FigureBuildJob(
        user_id=test_user.id,
        problem_text='[TEST K1] test problem for credit charge',
        status='queued',
        model_name='test-model',
        credit_charged=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(job)
    db.session.commit()

    credits_before = test_user.figure_credits
    tx_count_before = FigureCreditTransaction.query.filter_by(
        user_id=test_user.id,
    ).count()

    # Simulate the done transition + credit charge
    from routes.figures_generator import _charge_credit
    ok, msg = _charge_credit(job.id)

    # Re-fetch user from DB
    from models import User
    user = User.query.get(test_user.id)
    tx_count_after = FigureCreditTransaction.query.filter_by(
        user_id=test_user.id,
    ).count()

    assert ok, f"_charge_credit returned False: {msg}"
    assert user.figure_credits == credits_before - 1, (
        f"Expected {credits_before - 1}, got {user.figure_credits}"
    )
    assert tx_count_after == tx_count_before + 1, (
        f"Expected {tx_count_before + 1} transactions, got {tx_count_after}"
    )

    txn = FigureCreditTransaction.query.filter_by(
        user_id=test_user.id,
    ).order_by(FigureCreditTransaction.created_at.desc()).first()
    assert txn.amount == -1
    assert txn.reason == 'spend_ch5'
    assert str(job.id) in (txn.reference or '')
