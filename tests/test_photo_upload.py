# -*- coding: utf-8 -*-
"""Acceptance tests for photo upload hardening.

Covers: size limit (413), signature check, recognize-photo auth + rate limit,
explicit storage failure without S3 config, and HEIC rejection when the
converter is unavailable.
"""
import io
from datetime import datetime

import pytest

from models import db, PhotoRecognizeRequest


def _jpeg_bytes():
    """Return a minimal valid JPEG byte string."""
    return (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n'
        b'\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d'
        b'\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342'
        b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00'
        b'\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00'
        b'\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x03\x01\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07'
        b'\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xd2\xcf \xff\xd9'
    )


def _fake_heic_bytes():
    """Return bytes with a HEIC/HEIF `ftyp` signature (not a real image)."""
    return b'\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1'


def test_file_over_limit_rejected_413():
    from services.photo_upload import prepare_photo, PhotoError

    oversized = b'A' * (12 * 1024 * 1024 + 1)
    with pytest.raises(PhotoError) as exc:
        prepare_photo(oversized, 'image/jpeg', 'big.jpg')
    assert exc.value.status == 413


def test_wrong_signature_rejected_even_with_correct_mime():
    from services.photo_upload import prepare_photo, PhotoError

    # MIME says jpeg, but the bytes are not a valid image signature.
    bogus = b'not-an-image-at-all'
    with pytest.raises(PhotoError) as exc:
        prepare_photo(bogus, 'image/jpeg', 'fake.jpg')
    assert exc.value.status in (400, 415)


def test_recognize_photo_requires_login(client):
    """Route must not return 200 for an anonymous request."""
    resp = client.post('/api/figures/recognize-photo', json={'image': 'x'})
    assert resp.status_code in (302, 401)
    assert resp.status_code != 200


def test_recognize_photo_eleventh_request_429(app, auth_client, test_user):
    hour = datetime.utcnow().strftime('%Y-%m-%dT%H')
    for _ in range(10):
        db.session.add(PhotoRecognizeRequest(
            user_id=test_user.id, hour_bucket=hour, count=10,
        ))
    db.session.commit()

    resp = auth_client.post(
        '/api/figures/recognize-photo',
        json={'image': 'AA==', 'mime': 'image/jpeg'},
    )
    assert resp.status_code == 429
    body = resp.get_json() or {}
    assert body.get('error')


def test_upload_fails_without_s3_config(monkeypatch, tmp_path):
    import services.storage as storage
    from services.storage import StorageError

    monkeypatch.setattr(storage, 'R2_ACCOUNT_ID', '')
    monkeypatch.setattr(storage, 'R2_ACCESS_KEY_ID', '')
    monkeypatch.setattr(storage, 'R2_SECRET_ACCESS_KEY', '')
    monkeypatch.setattr(storage, 'PHOTO_LOCAL_FALLBACK', '')
    monkeypatch.setattr(storage, 'LOCAL_PHOTO_DIR', str(tmp_path))

    with pytest.raises(StorageError):
        storage.upload_photo(_jpeg_bytes(), user_id=1, content_type='image/jpeg')

    # Nothing must be written to local disk.
    written = list(tmp_path.rglob('*'))
    assert written == []


def test_heic_rejected_when_converter_unavailable(monkeypatch):
    from services.photo_upload import prepare_photo, PhotoError

    monkeypatch.setattr('services.photo_upload.HEIF_AVAILABLE', False)

    with pytest.raises(PhotoError) as exc:
        prepare_photo(_fake_heic_bytes(), 'image/heic', 'photo.heic')
    assert exc.value.status == 415
