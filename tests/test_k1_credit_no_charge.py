# -*- coding: utf-8 -*-
"""K1: Test NO credit charged on failed / cancel.

Uses F0 fixtures (app, test_user).
"""


def test_credit_not_charged_on_failed(app, test_user):
    """When job goes to failed, credit is never charged.

    If it WAS charged (by mistake), it gets refunded via _refund_credit.
    """
    from models import db, FigureBuildJob, FigureCreditTransaction
    from datetime import datetime

    test_user.figure_credits = 3
    db.session.commit()

    # Case A: failed without prior charge — credit stays
    job_a = FigureBuildJob(
        user_id=test_user.id,
        problem_text='[TEST K1] failed no charge',
        status='failed',
        model_name='test-model',
        credit_charged=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(job_a)
    db.session.commit()

    credits_a = test_user.figure_credits
    tx_count_a = FigureCreditTransaction.query.filter_by(
        user_id=test_user.id,
    ).count()

    from routes.figures_generator import _refund_credit
    _refund_credit(job_a.id)

    from models import User
    user = User.query.get(test_user.id)
    tx_after_a = FigureCreditTransaction.query.filter_by(
        user_id=test_user.id,
    ).count()

    # No charge, so no refund either — credits unchanged
    assert user.figure_credits == credits_a
    assert tx_after_a == tx_count_a

    # Case B: failed AFTER accidental charge — refund happens
    test_user.figure_credits = 3
    db.session.commit()

    job_b = FigureBuildJob(
        user_id=test_user.id,
        problem_text='[TEST K1] failed with accidental charge',
        status='failed',
        model_name='test-model',
        credit_charged=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(job_b)
    db.session.commit()

    credits_b = test_user.figure_credits
    tx_count_b = FigureCreditTransaction.query.filter_by(
        user_id=test_user.id,
    ).count()

    _refund_credit(job_b.id)

    user = User.query.get(test_user.id)
    tx_after_b = FigureCreditTransaction.query.filter_by(
        user_id=test_user.id,
    ).count()

    assert user.figure_credits == credits_b + 1, (
        f"Expected refund: credits should be {credits_b + 1}, "
        f"got {user.figure_credits}"
    )
    assert tx_after_b == tx_count_b + 1, "Expected one refund transaction added"

    refund_txn = FigureCreditTransaction.query.filter_by(
        user_id=test_user.id,
    ).order_by(FigureCreditTransaction.created_at.desc()).first()
    assert refund_txn.amount == 1
    assert refund_txn.reason == 'refund_ch5'


# NOT FOUND: separate cancel status.
# The FigureBuildJob model has statuses: queued, thinking, drawing, done, failed.
# There is no 'cancelled' or 'canceled' status and no cancel endpoint in the API.
# The task only tests this rule for failed.
