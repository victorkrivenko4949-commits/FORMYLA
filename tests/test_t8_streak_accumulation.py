# -*- coding: utf-8 -*-
"""T8: test streak accumulation — 3 days 100% -> streak=3, days_off=1."""
from datetime import date

from services.streak_service import get_or_create_streak, complete_day


def test_t8_streak_accumulation(app):
    """3 days 100% -> current_streak=3, days_off_available=1, max_streak=3."""
    with app.app_context():
        rec = get_or_create_streak(1)
        rec.current_streak = 0
        rec.max_streak = 0
        rec.days_off_available = 0

        complete_day(1, date(2026, 8, 1), True)
        assert rec.current_streak == 1
        assert rec.days_off_available == 0

        complete_day(1, date(2026, 8, 2), True)
        assert rec.current_streak == 2
        assert rec.days_off_available == 0

        complete_day(1, date(2026, 8, 3), True)
        assert rec.current_streak == 3
        assert rec.days_off_available == 1
        assert rec.max_streak == 3
