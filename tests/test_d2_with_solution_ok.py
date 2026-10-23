"""D2 accept 3: submit_ai with text solution returns 200 (or 503 if AI unavailable)."""

import pytest
import sys


def test_submit_ai_with_solution_ok(auth_client, daily_set_with_items):
    """POST /daily_tasks/<id>/submit_ai with non-empty solution_text."""
    from daily_tasks.models import DailyTaskItem
    item = DailyTaskItem.query.filter_by(daily_set_id=daily_set_with_items.id).first()
    assert item is not None, "daily_set_with_items should have at least one item"

    resp = auth_client.post(
        f"/daily_tasks/{item.id}/submit_ai",
        json={
            "user_answer": "42",
            "user_solution": "Решал через подстановку x=3",
            "solution_image_b64": "",
            "solution_images_b64": [],
        },
    )
    # With solution present, the endpoint should either return 200 (AI OK)
    # or 503 (AI unavailable). It must NOT return 400 (validation error).
    assert resp.status_code in (200, 503), (
        f"Expected 200 or 503, got {resp.status_code}: {resp.get_json()}"
    )
    if resp.status_code == 200:
        data = resp.get_json()
        assert data.get("status") == "success", (
            f"Expected status='success', got: {data}"
        )
