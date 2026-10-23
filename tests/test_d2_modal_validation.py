"""D2 accept 6: daily_tasks_modal.js contains solution check before submit."""

import pytest
import sys
import os


def test_modal_js_has_solution_check():
    """Verify daily_tasks_modal.js checks solution_text/solution_photo before fetch."""
    js_path = os.path.join(
        os.path.dirname(__file__), "..", "static", "js", "daily_tasks_modal.js"
    )
    assert os.path.isfile(js_path), f"File not found: {js_path}"

    with open(js_path, "r", encoding="utf-8") as f:
        content = f.read()

    # The modal should check for solution presence before submitting
    has_solution_check = (
        "DT_PHOTO_BUFFER" in content
        and "Опиши решение или прикрепи фото" in content
    )
    assert has_solution_check, (
        "daily_tasks_modal.js does not contain solution check: "
        "DT_PHOTO_BUFFER and 'Опиши решение или прикрепи фото' must both be present"
    )
