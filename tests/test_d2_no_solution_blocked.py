"""D2 accept 2: submit_ai blocks when no solution provided."""

import pytest
import sys


def test_submit_ai_no_solution_blocked(auth_client, daily_set_with_items):
    """POST /daily_tasks/<id>/submit_ai with empty solution returns 400."""
    from daily_tasks.models import DailyTaskItem
    item = DailyTaskItem.query.filter_by(daily_set_id=daily_set_with_items.id).first()
    assert item is not None, "daily_set_with_items should have at least one item"

    resp = auth_client.post(
        f"/daily_tasks/{item.id}/submit_ai",
        json={
            "user_answer": "42",
            "user_solution": "",
            "solution_image_b64": "",
            "solution_images_b64": [],
        },
    )
    data = resp.get_json()
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {data}"
    assert "error" in data, f"Expected 'error' key in response: {data}"
    assert "Опиши решение" in data["error"], (
        f"Expected 'Опиши решение' in error, got: {data['error']}"
    )
