# -*- coding: utf-8 -*-
"""T7: test idempotent activation — no duplicates."""
from models import db, User
from services.curator_plan_service import set_plan, activate_month


def test_t7_idempotent(app):
    """Double activate same month — still 7 rows, no duplicates."""
    with app.app_context():
        u = User(email='t7idem@test.ru', nickname='t7idem')
        u.current_month = 1
        db.session.add(u)
        db.session.commit()
        uid = u.id

        items = [(f"idem_{p}", 2, p) for p in range(1, 8)]
        set_plan(items)

        activate_month(uid, 2)
        activate_month(uid, 2)

        from models import UserSubtopicAssignment
        count = (UserSubtopicAssignment.query
                 .filter_by(user_id=uid, month_number=2)
                 .count())
        assert count == 7

        from sqlalchemy import func
        dups = (db.session.query(
            UserSubtopicAssignment.user_id,
            UserSubtopicAssignment.month_number,
            UserSubtopicAssignment.position,
            func.count(UserSubtopicAssignment.id),
        ).group_by(
            UserSubtopicAssignment.user_id,
            UserSubtopicAssignment.month_number,
            UserSubtopicAssignment.position,
        ).having(func.count(UserSubtopicAssignment.id) > 1).all())
        assert len(dups) == 0
