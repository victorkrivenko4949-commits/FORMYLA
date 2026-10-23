"""D2 accept 5: submit button is disabled by default in daily_task.html."""

import pytest
import sys
import os


def test_button_disabled_in_html():
    """Read daily_task.html file and check button disabled + hint text."""
    tmpl_path = os.path.join(
        os.path.dirname(__file__), "..", "templates", "daily_task.html"
    )
    assert os.path.isfile(tmpl_path), f"Template not found: {tmpl_path}"

    with open(tmpl_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Check submit button has disabled attribute
    assert 'id="submitBtn"' in html, "submitBtn id not found in template"
    assert "disabled" in html, "disabled attribute not found on submit button"

    # Check hint text is present
    assert "Опиши решение или прикрепи фото" in html, (
        "Hint text 'Опиши решение или прикрепи фото' not found"
    )

    # Check sticky positioning
    assert "position:sticky" in html, (
        "position:sticky not found on submit button"
    )

    # Check updateSubmitButtonState function exists
    assert "updateSubmitButtonState" in html, (
        "updateSubmitButtonState function not found in template JS"
    )
