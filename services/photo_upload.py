# -*- coding: utf-8 -*-
"""Shared photo validation, HEIC conversion, compression and storage.

All photo-upload routes read the allowed types and the size limit from this
single module so the rules cannot drift apart.
"""
import io
import logging

logger = logging.getLogger(__name__)

# ── Unified upload rules ──────────────────────────────────────────────
# MIME list mirrors the existing allowlist in routes/prep.py:1694 plus webp
# which is already accepted by the prep upload route (routes/prep.py:35).
ALLOWED_PHOTO_MIMES = {
    'image/jpeg',
    'image/png',
    'image/webp',
    'image/heic',
    'image/heif',
}
MAX_PHOTO_SIZE = 12 * 1024 * 1024  # 12 MB, single value for all three routes

# ── Pillow / pillow-heif imports (no silent pass) ─────────────────────
try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception as _pil_err:  # noqa: BLE001
    PIL_AVAILABLE = False
    logger.error(
        "Обработка изображений недоступна: не удалось импортировать модуль PIL: %s",
        _pil_err,
    )

try:
    import pillow_heif
    HEIF_AVAILABLE = True
except Exception as _heif_err:  # noqa: BLE001
    HEIF_AVAILABLE = False
    logger.error(
        "Обработка изображений недоступна: не удалось импортировать модуль pillow_heif: %s",
        _heif_err,
    )


class PhotoError(Exception):
    """User-facing photo upload error with an HTTP status."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def detect_photo_mime(photo_bytes):
    """Return a MIME type based on magic bytes, or None if unrecognized.

    Supported signatures: jpeg, png, webp, heic (no new packages).
    """
    if photo_bytes.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if photo_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if photo_bytes[:4] == b'RIFF' and photo_bytes[8:12] == b'WEBP':
        return 'image/webp'
    if photo_bytes[4:8] == b'ftyp':
        return 'image/heic'
    return None


def _convert_heic_to_jpeg(photo_bytes):
    """Convert HEIC bytes to JPEG using pillow-heif."""
    heif = pillow_heif.read_heif(photo_bytes)
    img = Image.frombytes(heif.mode, heif.size, heif.data, 'raw')
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=90)
    return buf.getvalue(), 'image/jpeg'


def _compress_to_jpeg(photo_bytes):
    """Resize to max 1500px long side and save as JPEG quality 80."""
    img = Image.open(io.BytesIO(photo_bytes))
    img = img.convert('RGB')
    w, h = img.size
    max_side = 1500
    if max(w, h) > max_side:
        ratio = max_side / max(w, h)
        w = int(w * ratio)
        h = int(h * ratio)
        img = img.resize((w, h), Image.LANCZOS)
    out_buf = io.BytesIO()
    img.save(out_buf, format='JPEG', quality=80)
    return out_buf.getvalue(), 'image/jpeg'


def prepare_photo(photo_bytes, content_type, filename):
    """Validate size, MIME and signature; convert HEIC; compress.

    Returns (photo_bytes, content_type).  Raises PhotoError on any problem.
    """
    if len(photo_bytes) == 0:
        raise PhotoError('Файл фотографии пуст.', 400)
    if len(photo_bytes) > MAX_PHOTO_SIZE:
        raise PhotoError('Размер фотографии превышает 12 МБ.', 413)

    # MIME from the request is client-controlled, so it is only a hint.
    content_type = content_type or 'application/octet-stream'
    ext_ok = any(
        filename.lower().endswith(ext)
        for ext in ('.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif')
    )
    if content_type not in ALLOWED_PHOTO_MIMES and not ext_ok:
        raise PhotoError(
            'Неподдерживаемый формат. Принимаются jpg, png, webp, heic.', 415,
        )

    # Signature check from first bytes — cannot be spoofed by the client MIME.
    signature = detect_photo_mime(photo_bytes)
    if signature is None:
        raise PhotoError('Не удалось распознать формат изображения.', 400)
    if signature not in {'image/jpeg', 'image/png', 'image/webp', 'image/heic'}:
        raise PhotoError('Неподдерживаемый формат изображения.', 400)

    is_heic = (
        content_type in ('image/heic', 'image/heif')
        or filename.lower().endswith(('.heic', '.heif'))
        or signature == 'image/heic'
    )
    if is_heic:
        if not HEIF_AVAILABLE:
            raise PhotoError(
                'Загрузка HEIC недоступна: конвертер изображений не установлен.', 415,
            )
        photo_bytes, content_type = _convert_heic_to_jpeg(photo_bytes)

    # Normalise to JPEG when Pillow is available.  If Pillow is missing we
    # cannot process the image; a HEIC file would already have been rejected
    # above, but for other formats we keep the original bytes.
    if PIL_AVAILABLE:
        try:
            photo_bytes, content_type = _compress_to_jpeg(photo_bytes)
        except Exception as _compress_err:
            logger.error(
                "Обработка изображений недоступна: не удалось обработать изображение (PIL): %s",
                _compress_err,
            )
    else:
        logger.error(
            "Обработка изображений недоступна: модуль PIL не загружен, "
            "фото сохранено без обработки."
        )

    return photo_bytes, content_type


def store_photo(photo_bytes, user_id, content_type):
    """Upload prepared bytes to storage and return (url, photo_hash)."""
    from services.storage import upload_photo, StorageError

    try:
        url, photo_hash = upload_photo(photo_bytes, user_id, content_type)
    except StorageError as exc:
        logger.error("Не удалось сохранить фото пользователя %s: %s", user_id, exc)
        raise PhotoError(str(exc), 500)
    return url, photo_hash
