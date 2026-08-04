# -*- coding: utf-8 -*-
"""T7: test missing month — plan_missing flag, empty subtopics."""
import logging

from models import db, User
from services.curator_plan_service import set_plan, activate_month, advance_study_month, get_active_subtopics


def test_t7_missing_month(app):
    """Advance past planned months -> plan_missing, empty subtopics."""
    with app.app_context():
        u = User(email='t7miss@test.ru', nickname='t7miss')
        u.current_month = 1
        u.role = 'student'
        db.session.add(u)
        db.session.commit()
        uid = u.id

        items = []
        for m in range(1, 4):
            for p in range(1, 8):
                items.append((f"m{m}p{p}", m, p))
        set_plan(items)

        activate_month(uid, 1)
        advance_study_month(uid)  # -> month 2
        advance_study_month(uid)  # -> month 3

        r = advance_study_month(uid)  # -> month 4 (no plan)
        assert r['new_month'] == 4
        assert r['plan_missing'] is True

        assignments, status = get_active_subtopics(uid)
        assert status['plan_missing'] is True
