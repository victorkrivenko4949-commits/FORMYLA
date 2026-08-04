# -*- coding: utf-8 -*-
"""T8: test day-off preserves streak and doesn't touch mu/sigma."""
from datetime import date

from models import db
from services.streak_service import get_or_create_streak, complete_day, take_day_off


def test_t8_day_off_preserves(app):
    """Take day-off: streak stays, days_off decreases, mu/sigma unchanged."""
    with app.app_context():
        rec = get_or_create_streak(1)
        rec.current_streak = 3
        rec.max_streak = 3
        rec.days_off_available = 1
        rec.last_solved_date = date(2026, 8, 3)
        db.session.flush()

        ok = take_day_off(1, date(2026, 8, 4))
        assert ok is True
        assert rec.current_streak == 3
        assert rec.days_off_available == 0
        assert rec.last_solved_date == date(2026, 8, 4)
