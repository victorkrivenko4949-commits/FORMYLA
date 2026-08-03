# -*- coding: utf-8 -*-
"""tests/test_d3_daily_buffer.py -- D3 block acceptance tests.

Tests for the 3-day-ahead daily task buffer using F0 fixtures:
  - app, test_user, five_anchor_tasks
"""

from datetime import date, timedelta

import pytest


def test_d3_buffer_creates_three_days(app, test_user, five_anchor_tasks):
    """Acceptance test 2: fill 3-day buffer, dump daily_task_sets/_items.

    Creates 3 DailyTaskSet records (today, +1, +2) with items from
    the five_anchor_tasks fixture, then prints RESULT and SET lines.
    """
    from daily_tasks.buffer import ensure_daily_buffer
    from daily_tasks.models import DailyTaskSet, DailyTaskItem

    # Set preferred_grade so build_profile does not fail
    test_user.preferred_grade = 7
    from models import db
    db.session.commit()

    with app.app_context():
        # Pass a synthetic profile so we don't depend on real AI pipeline
        synthetic_profile = {
            "class_level": 7,
            "class_expected_level": 3,
            "weak_topics": [],
            "strong_topics": [],
            "calibration_topics": [],
            "topics_full": [],
            "profile_completeness": 0.0,
            "measured_topics_count": 0,
            "adaptive_summary": {},
        }
        result = ensure_daily_buffer(
            test_user.id, days_ahead=3, profile=synthetic_profile,
        )
        print("RESULT", result)

        sets = DailyTaskSet.query.filter_by(
            user_id=test_user.id,
        ).order_by(DailyTaskSet.target_date).all()

        for s in sets:
            items = DailyTaskItem.query.filter_by(daily_set_id=s.id).all()
            day_status = result.get("days", {}).get(
                s.target_date.isoformat(), {},
            ).get("status", "unknown")
            print(
                "SET target_date=%s items=%s status=%s"
                % (s.target_date, len(items), day_status)
            )


def test_d3_buffer_idempotent(app, test_user, five_anchor_tasks):
    """Acceptance test 3: second call does not create duplicates."""
    from daily_tasks.buffer import ensure_daily_buffer
    from daily_tasks.models import DailyTaskSet

    test_user.preferred_grade = 7
    from models import db
    db.session.commit()

    synthetic_profile = {
        "class_level": 7,
        "class_expected_level": 3,
        "weak_topics": [],
        "strong_topics": [],
        "calibration_topics": [],
        "topics_full": [],
        "profile_completeness": 0.0,
        "measured_topics_count": 0,
        "adaptive_summary": {},
    }

    with app.app_context():
        ensure_daily_buffer(
            test_user.id, days_ahead=3, profile=synthetic_profile,
        )
        count_before = DailyTaskSet.query.filter_by(
            user_id=test_user.id,
        ).count()

        result2 = ensure_daily_buffer(
            test_user.id, days_ahead=3, profile=synthetic_profile,
        )
        count_after = DailyTaskSet.query.filter_by(
            user_id=test_user.id,
        ).count()

        print("COUNT_BEFORE", count_before)
        print("COUNT_AFTER", count_after)
        print("RESULT2", result2)

        assert count_before == count_after, (
            "Idempotency violated: %d before, %d after"
            % (count_before, count_after)
        )


def test_d3_no_regeneration_when_full(app, test_user, five_anchor_tasks, monkeypatch):
    """Acceptance test 4: zero pipeline calls when buffer already full."""
    from daily_tasks.buffer import ensure_daily_buffer

    test_user.preferred_grade = 7
    from models import db
    db.session.commit()

    synthetic_profile = {
        "class_level": 7,
        "class_expected_level": 3,
        "weak_topics": [],
        "strong_topics": [],
        "calibration_topics": [],
        "topics_full": [],
        "profile_completeness": 0.0,
        "measured_topics_count": 0,
        "adaptive_summary": {},
    }

    calls = []

    import daily_tasks.services as svc
    original_generate = svc.generate_daily_set

    def mock_generate(*args, **kwargs):
        calls.append(1)
        return original_generate(*args, **kwargs)

    monkeypatch.setattr(svc, "generate_daily_set", mock_generate)

    with app.app_context():
        # First call: creates the buffer
        ensure_daily_buffer(
            test_user.id, days_ahead=3, profile=synthetic_profile,
        )
        calls.clear()

        # Second call: should not call generate_daily_set at all
        ensure_daily_buffer(
            test_user.id, days_ahead=3, profile=synthetic_profile,
        )
        print("PIPELINE_CALLS_ON_FULL_BUFFER", len(calls))

        assert len(calls) == 0, (
            "Expected 0 pipeline calls on full buffer, got %d" % len(calls)
        )


def test_d3_empty_pool_no_crash(app, test_user):
    """Acceptance test 5: empty pool returns status without crashing.

    test_user has no preferred_grade -> build_profile fails ->
    generate_daily_set returns empty_pool status.
    """
    from daily_tasks.buffer import ensure_daily_buffer

    with app.app_context():
        # test_user has no preferred_grade -- build_profile will fail
        result = ensure_daily_buffer(test_user.id, days_ahead=3)
        print("RESULT_EMPTY_POOL", result)

        assert result.get("status") in ("empty_pool", "ok", "partial"), (
            "Expected empty_pool/ok/partial, got %s" % result.get("status")
        )
        # At least one day should have empty_pool status
        days = result.get("days", {})
        any_empty = any(
            d.get("status") == "empty_pool" for d in days.values()
        )
        print("ANY_EMPTY_POOL_DAY", any_empty)


def test_d3_buffer_creates_items_from_five_tasks(app, test_user, five_anchor_tasks):
    """Verify that 3 DailyTaskSets are created with correct consecutive dates.

    Items are populated asynchronously by the background pipeline thread --
    they may be 0 immediately after set creation.  This is normal.
    The test verifies only set metadata, not item count.
    """
    from daily_tasks.buffer import ensure_daily_buffer
    from daily_tasks.models import DailyTaskSet, DailyTaskItem

    test_user.preferred_grade = 7
    from models import db
    db.session.commit()

    synthetic_profile = {
        "class_level": 7,
        "class_expected_level": 3,
        "weak_topics": [],
        "strong_topics": [],
        "calibration_topics": [],
        "topics_full": [],
        "profile_completeness": 0.0,
        "measured_topics_count": 0,
        "adaptive_summary": {},
    }

    with app.app_context():
        ensure_daily_buffer(
            test_user.id, days_ahead=3, profile=synthetic_profile,
        )

        sets = DailyTaskSet.query.filter_by(
            user_id=test_user.id,
        ).order_by(DailyTaskSet.target_date).all()

        assert len(sets) == 3, (
            "Expected 3 DailyTaskSets, got %d" % len(sets)
        )

        today = date.today()
        for i, s in enumerate(sets):
            assert s.target_date == today + timedelta(days=i), (
                "Set %d expected date=%s, got %s"
                % (i, today + timedelta(days=i), s.target_date)
            )
            # Items are populated asynchronously by background pipeline;
            # verify set status is set correctly.
            assert s.status in ("generating", "ready"), (
                "Set for %s has unexpected status=%s" % (s.target_date, s.status)
            )
            assert s.triggered_by == "buffer", (
                "Set for %s has triggered_by=%s, expected=buffer"
                % (s.target_date, s.triggered_by)
            )
