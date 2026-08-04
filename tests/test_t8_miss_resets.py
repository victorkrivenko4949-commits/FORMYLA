# -*- coding: utf-8 -*-
"""T8: test miss without day-off resets streak."""
from datetime import date

from services.streak_service import get_or_create_streak, check_streak_on_open


def test_t8_miss_resets(app):
    """Gap >1 day without day-off -> streak=0, days_off_available=0."""
    with app.app_context():
        rec = get_or_create_streak(1)
        rec.current_streak = 3
        rec.max_streak = 3
        rec.days_off_available = 1
        rec.last_solved_date = date(2026, 8, 3)

        check_streak_on_open(1, date(2026, 8, 5))
        assert rec.current_streak == 0
        assert rec.days_off_available == 0
