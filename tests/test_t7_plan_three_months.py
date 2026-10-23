# -*- coding: utf-8 -*-
"""T7: test plan three months — activate and advance."""
from models import db, User
from services.curator_plan_service import set_plan, activate_month, advance_study_month


def test_t7_plan_three_months(app):
    """set_plan 21 items, activate month 1, advance to 2 and 3."""
    with app.app_context():
        u = User(email='t7test@test.ru', nickname='t7test')
        u.current_month = 1
        db.session.add(u)
        db.session.commit()
        uid = u.id

        items = []
        for m in range(1, 4):
            for p in range(1, 8):
                items.append((f"subtopic_m{m}_p{p}", m, p))
        set_plan(items)

        r = activate_month(uid, 1)
        assert r['plan_missing'] is False

        r2 = advance_study_month(uid)
        assert r2['new_month'] == 2
        assert r2['plan_missing'] is False

        r3 = advance_study_month(uid)
        assert r3['new_month'] == 3
        assert r3['plan_missing'] is False
