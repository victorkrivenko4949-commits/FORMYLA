"""D1: test that daily task text solution creates SolutionAttempt with attempt_type='daily'."""

import pytest
from models import db, SolutionAttempt
from daily_tasks.models import DailyTaskItem


def test_daily_text_solution_creates_solution_attempt(auth_client, daily_set_with_items):
    """Sending text solution on daily task must create one SolutionAttempt row
    with attempt_type='daily'."""
    items = DailyTaskItem.query.filter_by(
        daily_set_id=daily_set_with_items.id
    ).order_by(DailyTaskItem.position).all()

    assert len(items) >= 3, "Need at least 3 items in fixture"

    item = items[2]  # use third item (first two used in other tests)
    before_count = SolutionAttempt.query.count()

    resp = auth_client.post(
        f"/daily_tasks/{item.id}/submit",
        json={
            "answer": "42",
            "solution_method": "text",
            "solution_text": "Решение: x = 42, потому что ответ на главный вопрос.",
        },
    )
    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code}: {resp.get_data(as_text=True)}"
    )

    after_count = SolutionAttempt.query.count()
    assert after_count == before_count + 1, (
        f"Expected exactly 1 new SolutionAttempt. Before: {before_count}, After: {after_count}"
    )

    # Get the last created attempt
    attempt = SolutionAttempt.query.order_by(SolutionAttempt.id.desc()).first()
    assert attempt is not None, "SolutionAttempt was not created"
    assert attempt.attempt_type == 'daily', (
        f"Expected attempt_type='daily', got '{attempt.attempt_type}'"
    )
    assert attempt.solution_text is not None, "solution_text must be non-null"
    assert len(attempt.solution_text) > 0, "solution_text must be non-empty"
    # probe_id must be null for daily tasks
    assert attempt.probe_id is None, f"probe_id must be None for daily, got {attempt.probe_id}"
