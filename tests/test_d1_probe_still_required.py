"""D1: test that probe (slice) submission WITHOUT solution still returns 400."""

import pytest
from io import BytesIO


def test_probe_submit_without_solution_still_400(auth_client, five_anchor_tasks):
    """Probe (slice) must still require solution - return 400 if missing."""
    from models import db
    from models import AdaptiveTask

    task = five_anchor_tasks[0]

    # Use the prep answer endpoint that was built in D9 layer
    resp = auth_client.post(
        "/prep/answer",
        json={
            "task_id": task.id,
            "answer": "test_answer",
            "solution_method": "text",
            "solution_text": "",
        },
    )
    # Probe should still reject with 400 when solution is missing
    assert resp.status_code == 400, (
        f"Expected 400 for probe without solution, got {resp.status_code}: "
        f"{resp.get_data(as_text=True)}"
    )
