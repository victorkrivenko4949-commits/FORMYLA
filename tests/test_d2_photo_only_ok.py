"""D2 accept 4: submit_ai with base64 photo (no text) works."""

import pytest
import sys
import base64


# Minimal valid JPEG base64: 1x1 white pixel
_MINI_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsL"
    "DBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/"
    "2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
    "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QA"
    "HwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUF"
    "BAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkK"
    "FhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1"
    "dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXG"
    "x8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEB"
    "AQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAEC"
    "AxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYI5Ki"
    "o8QFU3RTVFVmcoaEorK0ys4TNkdTVHaWt7C4uP4TFBYXGBkaJic3/9oADAMB"
    "AAIRAxEAPwDx+iiigD/2Q=="
)


def test_submit_ai_photo_only_ok(auth_client, daily_set_with_items):
    """POST /daily_tasks/<id>/submit_ai with base64 photo, no text."""
    from daily_tasks.models import DailyTaskItem
    item = DailyTaskItem.query.filter_by(daily_set_id=daily_set_with_items.id).first()
    assert item is not None, "daily_set_with_items should have at least one item"

    resp = auth_client.post(
        f"/daily_tasks/{item.id}/submit_ai",
        json={
            "user_answer": "42",
            "user_solution": "",
            "solution_image_b64": _MINI_JPEG_B64,
            "solution_images_b64": [_MINI_JPEG_B64],
        },
    )
    # With photo present, validation passes. AI may be 200 or 503, not 400.
    assert resp.status_code in (200, 503), (
        f"Expected 200 or 503, got {resp.status_code}: {resp.get_json()}"
    )
    if resp.status_code == 200:
        data = resp.get_json()
        assert data.get("status") == "success", (
            f"Expected status='success', got: {data}"
        )
