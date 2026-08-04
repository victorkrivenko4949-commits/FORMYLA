# -*- coding: utf-8 -*-
"""
services/streak_service.py — T8 daily quest streak and days-off logic.

One StreakRecord per user.  Updated on daily task set completion,
on-open checks, and explicit day-off requests.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from models import db, StreakRecord

logger = logging.getLogger(__name__)

STREAK_DAYS_FOR_DAY_OFF = 3  # every 3 days of streak grant 1 day-off


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def get_or_create_streak(user_id: int) -> StreakRecord:
    """Return the StreakRecord for *user_id*, creating one if missing."""
    rec = StreakRecord.query.filter_by(user_id=user_id).first()
    if rec is None:
        rec = StreakRecord(user_id=user_id)
        db.session.add(rec)
        db.session.flush()
    return rec


def check_streak_on_open(user_id: int, today: date) -> StreakRecord:
    """Called when the user opens the daily tasks page.

    If the user has a last_solved_date and it is older than
    ``today - 1 day`` AND they had no day-off taken, the streak
    is reset to 0.  Otherwise the streak is left untouched.
    """
    rec = get_or_create_streak(user_id)

    if rec.last_solved_date is not None:
        gap = (today - rec.last_solved_date).days
        # Gap of 1 day (= yesterday) is fine — streak is preserved.
        # Gap of >1 day without a day-off means the streak is broken.
        if gap > 1:
            rec.current_streak = 0
            rec.days_off_available = 0
            db.session.flush()

    return rec


def complete_day(user_id: int, today: date, all_correct: bool) -> StreakRecord:
    """Called after the daily task set is fully answered.

    *all_correct* must be ``True`` only when every item in the set
    was answered correctly (+1).  Partial (0) or wrong (-2) answers
    mean ``all_correct=False``.

    On 100%:
        current_streak += 1
        max_streak = max(max_streak, current_streak)
        Every STREAK_DAYS_FOR_DAY_OFF days -> days_off_available += 1

    On not 100%:
        current_streak = 0
        days_off_available = 0

    Always:
        last_solved_date = today
    """
    rec = get_or_create_streak(user_id)

    if all_correct:
        rec.current_streak = (rec.current_streak or 0) + 1
        rec.max_streak = max(rec.max_streak or 0, rec.current_streak)
        if rec.current_streak % STREAK_DAYS_FOR_DAY_OFF == 0:
            rec.days_off_available = (rec.days_off_available or 0) + 1
    else:
        rec.current_streak = 0
        rec.days_off_available = 0

    rec.last_solved_date = today
    db.session.flush()
    return rec


def take_day_off(user_id: int, today: date) -> bool:
    """Consume one day-off token.  mu/sigma are NOT touched.

    Returns True on success, False if no days-off available.
    """
    rec = get_or_create_streak(user_id)

    if not rec.days_off_available or rec.days_off_available <= 0:
        return False

    rec.days_off_available -= 1
    rec.last_solved_date = today  # mark today as "covered"
    # current_streak stays unchanged
    db.session.flush()
    return True


# ---------------------------------------------------------------------------
# Helper for the route layer
# ---------------------------------------------------------------------------

def compute_all_correct(daily_set_id: int) -> bool:
    """Return True when every item of the set is answered correctly."""
    from daily_tasks.models import DailyTaskItem

    items = DailyTaskItem.query.filter_by(daily_set_id=daily_set_id).all()
    if not items:
        return False
    for it in items:
        if it.user_answer is None:
            return False
        if not it.is_correct:
            return False
    return True


def set_is_fully_answered(daily_set_id: int) -> bool:
    """Return True when every item has a non-null user_answer."""
    from daily_tasks.models import DailyTaskItem

    items = DailyTaskItem.query.filter_by(daily_set_id=daily_set_id).all()
    if not items:
        return False
    return all(it.user_answer is not None for it in items)
