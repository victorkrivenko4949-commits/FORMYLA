"""D1: test that daily task submission WITHOUT solution succeeds (200)."""

import pytest
from models import db
from daily_tasks.models import DailyTaskItem, DailyTaskSet


def test_daily_submit_without_solution(auth_client, daily_set_with_items):
    """Submit answer on daily task without solution text or file - must succeed with 200."""
    items = DailyTaskItem.query.filter_by(
        daily_set_id=daily_set_with_items.id
    ).order_by(DailyTaskItem.position).all()

    assert len(items) >= 1, "daily_set_with_items must have at least 1 item"

    item = items[0]
    resp = auth_client.post(
        f"/daily_tasks/{item.id}/submit",
        json={"answer": "test_answer", "solution_method": "text", "solution_text": ""},
    )
    assert resp.status_code == 200, (
        f"Expected 200 for daily task without solution, got {resp.status_code}: "
        f"{resp.get_data(as_text=True)}"
    )

    data = resp.get_json()
    assert "is_correct" in data or "success" in data, (
        f"Response must contain is_correct or success, got keys: {list(data.keys())}"
    )


def test_no_solution_attempt_created_without_solution(auth_client, daily_set_with_items):
    """When no solution is sent, no SolutionAttempt row should be created."""
    items = DailyTaskItem.query.filter_by(
        daily_set_id=daily_set_with_items.id
    ).order_by(DailyTaskItem.position).all()

    item = items[1]  # use second item

    # Count existing solution_attempts
    from models import SolutionAttempt
    before_count = SolutionAttempt.query.count()

    resp = auth_client.post(
        f"/daily_tasks/{item.id}/submit",
        json={"answer": "another_answer", "solution_method": "text", "solution_text": ""},
    )
    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code}: {resp.get_data(as_text=True)}"
    )

    after_count = SolutionAttempt.query.count()
    assert after_count == before_count, (
        f"SolutionAttempt count changed: {before_count} -> {after_count}. "
        f"No solution was sent, so no record should be created."
    )
