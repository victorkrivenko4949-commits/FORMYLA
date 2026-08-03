"""D1: test that daily task photo solution saves file to correct path."""

import pytest
from io import BytesIO
from datetime import datetime
from models import db, SolutionAttempt
from daily_tasks.models import DailyTaskItem


def _make_jpeg_bytes():
    """Generate a minimal valid JPEG in memory."""
    import struct
    # Minimal JPEG: SOI + APP0 + DQT + SOF0 + DHT + SOS + EOI
    # Using a known minimal valid JPEG
    jpeg = (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n'
        b'\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d'
        b'\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342'
        b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00'
        b'\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00'
        b'\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00'
        b'\x08\x01\x01\x00\x00?\x00\xd2\xcf \xff\xd9'
    )
    return jpeg


def test_daily_photo_file_saved_to_correct_path(auth_client, daily_set_with_items, app):
    """Photo uploaded as solution must save to uploads/solutions/<YYYY-MM>/<random>.jpg
    and file_path in SolutionAttempt must contain correct substrings."""
    items = DailyTaskItem.query.filter_by(
        daily_set_id=daily_set_with_items.id
    ).order_by(DailyTaskItem.position).all()

    assert len(items) >= 4, "Need at least 4 items in fixture"

    item = items[3]  # use fourth item

    jpeg_bytes = _make_jpeg_bytes()
    data = {
        "answer": "99",
        "solution_method": "photo",
    }
    # Flask test client: send file via data dict with file wrapper
    resp = auth_client.post(
        f"/daily_tasks/{item.id}/submit",
        data={
            "answer": "99",
            "solution_method": "photo",
            "solution_photo": (BytesIO(jpeg_bytes), "test_solution.jpg"),
        },
        content_type="multipart/form-data",
    )

    # Check response
    response_data = resp.get_json(silent=True) or {}
    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code}: {resp.get_data(as_text=True)}"
    )

    # Check SolutionAttempt record
    attempt = SolutionAttempt.query.order_by(SolutionAttempt.id.desc()).first()
    assert attempt is not None, "SolutionAttempt must be created for photo upload"
    assert attempt.attempt_type == 'daily', (
        f"Expected attempt_type='daily', got '{attempt.attempt_type}'"
    )

    file_path = attempt.file_path
    assert file_path is not None, "file_path must be non-null for photo solution"

    # Check path contains expected substrings
    year_month = datetime.utcnow().strftime('%Y-%m')
    assert 'uploads/solutions/' in file_path, (
        f"file_path must contain 'uploads/solutions/', got: {file_path}"
    )
    assert year_month in file_path, (
        f"file_path must contain '{year_month}', got: {file_path}"
    )
    assert file_path.endswith('.jpg'), (
        f"file_path must end with '.jpg', got: {file_path}"
    )

    # Check file_size > 0
    assert attempt.file_size is not None, "file_size must be non-null"
    assert attempt.file_size > 0, f"file_size must be >0, got {attempt.file_size}"
