# -*- coding: utf-8 -*-
"""
services/curator_plan_service.py — T7 curator plan: monthly subtopic rotation.

Curator sets a global plan template (7 subtopics per month).
Each student auto-advances through months.  Idempotent activation
prevents duplicates on repeated calls.
"""
from __future__ import annotations

import logging
from typing import List, Tuple, Dict, Optional

from models import db, User
from models import CuratorPlanItem, UserSubtopicAssignment

logger = logging.getLogger(__name__)

SUBS_PER_MONTH = 7


# ---------------------------------------------------------------------------
# Plan management (curator)
# ---------------------------------------------------------------------------

def set_plan(items: List[Tuple[str, int, int]]) -> None:
    """Replace the entire global plan.

    *items* is a list of (subtopic, month_number, position).
    Clears curator_plan_items and inserts fresh rows.
    """
    CuratorPlanItem.query.delete()
    for subtopic, month_number, position in items:
        db.session.add(CuratorPlanItem(
            subtopic=subtopic,
            month_number=month_number,
            position=position,
        ))
    db.session.commit()
    logger.info("curator_plan: set %d items across %d months",
                len(items),
                len({m for _, m, _ in items}))


def get_plan_items(month_number: int) -> List[CuratorPlanItem]:
    """Return all plan items for a given month, ordered by position."""
    return (CuratorPlanItem.query
            .filter_by(month_number=month_number)
            .order_by(CuratorPlanItem.position)
            .all())


# ---------------------------------------------------------------------------
# Student activation
# ---------------------------------------------------------------------------

def activate_month(user_id: int, month_number: int) -> Dict:
    """Activate a month for a user: copy plan items into assignments.

    Returns dict with keys: plan_missing (bool), count (int).
    Idempotent — duplicate calls don't create duplicate rows.
    """
    plan_items = get_plan_items(month_number)
    if not plan_items:
        logger.warning("план на месяц %d не задан", month_number)
        return {'plan_missing': True, 'count': 0}

    # UPSERT via try/except — UNIQUE constraint prevents duplicates
    count = 0
    for pi in plan_items:
        try:
            existing = UserSubtopicAssignment.query.filter_by(
                user_id=user_id, month_number=month_number, position=pi.position,
            ).first()
            if existing:
                continue
            db.session.add(UserSubtopicAssignment(
                user_id=user_id,
                subtopic=pi.subtopic,
                month_number=month_number,
                position=pi.position,
            ))
            count += 1
        except Exception:
            db.session.rollback()
            logger.exception("activate_month: insert failed u%d m%d p%d",
                             user_id, month_number, pi.position)
            continue
    db.session.commit()

    logger.info("activate_month: user=%d month=%d inserted=%d",
                user_id, month_number, count)
    return {'plan_missing': False, 'count': count}


def get_active_subtopics(user_id: int) -> Tuple[List[UserSubtopicAssignment], Dict]:
    """Return active subtopic assignments for user's current_month.

    Returns (assignments, status_dict).
    status_dict has plan_missing (bool) — True if no assignments found.
    """
    user = User.query.get(user_id)
    if not user:
        return [], {'plan_missing': True}

    cm = getattr(user, 'current_month', None) or 1
    assignments = (UserSubtopicAssignment.query
                   .filter_by(user_id=user_id, month_number=cm)
                   .order_by(UserSubtopicAssignment.position)
                   .all())

    plan_missing = len(assignments) < SUBS_PER_MONTH
    if plan_missing:
        logger.info("get_active_subtopics: user=%d month=%d found=%d (plan_missing)",
                    user_id, cm, len(assignments))

    return assignments, {'plan_missing': plan_missing, 'month': cm, 'count': len(assignments)}


def advance_study_month(user_id: int) -> Dict:
    """Increment user.current_month and activate the new month.

    Idempotent: if the new month already has assignments, current_month
    is set but no duplicates are inserted.

    Returns dict with: new_month (int), plan_missing (bool), count (int).
    """
    user = User.query.get(user_id)
    if not user:
        return {'new_month': 0, 'plan_missing': True, 'count': 0}

    current = getattr(user, 'current_month', None) or 1
    new_month = current + 1

    # Check if already advanced (idempotency)
    existing = (UserSubtopicAssignment.query
                .filter_by(user_id=user_id, month_number=new_month)
                .count())
    if existing > 0:
        user.current_month = new_month
        db.session.commit()
        return {'new_month': new_month, 'plan_missing': False, 'count': existing}

    user.current_month = new_month
    db.session.commit()
    result = activate_month(user_id, new_month)
    return {'new_month': new_month, 'plan_missing': result['plan_missing'],
            'count': result['count']}


# ---------------------------------------------------------------------------
# Curator dashboard
# ---------------------------------------------------------------------------

def check_plan_status() -> Dict:
    """Return plan completeness info for the curator dashboard.

    Returns dict with:
        months_in_plan: set of month numbers that have 7 items each
        missing_months: list of month numbers missing plan
        students_plan_missing: list of user_ids whose current_month has < 7 assignments
    """
    # Which months have a complete plan?
    from sqlalchemy import func
    rows = (db.session.query(
        CuratorPlanItem.month_number,
        func.count(CuratorPlanItem.id),
    ).group_by(CuratorPlanItem.month_number).all())

    months_in_plan = {int(r[0]) for r in rows if r[1] >= SUBS_PER_MONTH}

    # Missing future months (up to the highest planned + 1)
    max_month = max(months_in_plan) if months_in_plan else 0
    missing_months = [m for m in range(1, max_month + 2)
                      if m not in months_in_plan]

    # Students with missing assignments for their current month
    users = User.query.all()
    students_missing = []
    for u in users:
        cm = getattr(u, 'current_month', None) or 1
        cnt = (UserSubtopicAssignment.query
               .filter_by(user_id=u.id, month_number=cm)
               .count())
        if cnt < SUBS_PER_MONTH:
            students_missing.append({'user_id': u.id, 'month': cm, 'count': cnt})

    return {
        'months_in_plan': sorted(months_in_plan),
        'missing_months': missing_months,
        'students_plan_missing': students_missing,
    }
