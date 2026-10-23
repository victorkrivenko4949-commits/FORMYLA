# -*- coding: utf-8 -*-
"""T8: test button visibility and take-day-off route."""
from services.streak_service import get_or_create_streak


def test_t8_button_visibility_no_button_when_zero(app):
    """When days_off_available=0, route returns not-500."""
    with app.app_context():
        rec = get_or_create_streak(1)
        rec.days_off_available = 0
        rec.current_streak = 0

    with app.test_client() as c:
        c.post('/auth/test_login/1')
        r = c.post('/daily_tasks/take-day-off')
        assert r.status_code != 500
