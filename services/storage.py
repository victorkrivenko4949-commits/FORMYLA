# -*- coding: utf-8 -*-
"""
Cloudflare R2 / S3-compatible storage for handwritten solution photos.

Environment variables:
  R2_ACCOUNT_ID       — Cloudflare account ID
  R2_ACCESS_KEY_ID    — R2 access key
  R2_SECRET_ACCESS_KEY — R2 secret key
  R2_BUCKET_NAME      — bucket name (default: formyla-photos)
  R2_PUBLIC_URL       — public URL prefix (e.g. https://photos.formyla.ru)

Falls back to local filesystem storage if R2 is not configured.
"""
import hashlib
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# R2 / S3 config
R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID', '')
R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID', '')
R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY', '')
R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME', 'formyla-photos')
R2_PUBLIC_URL = os.environ.get('R2_PUBLIC_URL', '')

# Local fallback directory
LOCAL_PHOTO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'uploads', 'photos')


def compute_photo_hash(photo_bytes):
    """Compute SHA256 hash of photo bytes."""
    return hashlib.sha256(photo_bytes).hexdigest()


def dedupe_check(photo_hash):
    """Check if a photo with this hash already exists in DB."""
    from models import TaskSolution
    return TaskSolution.query.filter_by(photo_hash=photo_hash).first() is not None


def upload_photo(photo_bytes, user_id, content_type='image/jpeg'):
    """
    Upload photo to R2 (or local fallback). Returns (url, hash).

    Args:
        photo_bytes: raw image bytes
        user_id: user ID for path namespacing
        content_type: MIME type (default: image/jpeg)

    Returns:
        tuple: (public_url: str, photo_hash: str)
    """
    photo_hash = compute_photo_hash(photo_bytes)

    # Determine file extension from content type
    ext_map = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/webp': '.webp',
        'image/heic': '.heic',
    }
    ext = ext_map.get(content_type, '.jpg')
    key = f"photos/{user_id}/{photo_hash}{ext}"

    if _r2_configured():
        url = _upload_to_r2(photo_bytes, key, content_type)
    else:
        url = _upload_to_local(photo_bytes, key)

    return url, photo_hash


def _r2_configured():
    """Check if R2 credentials are available."""
    return bool(R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY)


def _upload_to_r2(photo_bytes, key, content_type):
    """Upload to Cloudflare R2 via S3-compatible API."""
    try:
        import boto3
        from botocore.config import Config

        endpoint_url = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

        s3 = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )

        s3.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=key,
            Body=photo_bytes,
            ContentType=content_type,
        )

        if R2_PUBLIC_URL:
            url = f"{R2_PUBLIC_URL.rstrip('/')}/{key}"
        else:
            url = f"{endpoint_url}/{R2_BUCKET_NAME}/{key}"

        logger.info(f"Uploaded to R2: {key} ({len(photo_bytes)} bytes)")
        return url

    except Exception as e:
        logger.error(f"R2 upload failed: {e}, falling back to local")
        return _upload_to_local(photo_bytes, key)


def _upload_to_local(photo_bytes, key):
    """Fallback: save to local filesystem."""
    filepath = os.path.join(LOCAL_PHOTO_DIR, key)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, 'wb') as f:
        f.write(photo_bytes)

    logger.info(f"Saved locally: {filepath} ({len(photo_bytes)} bytes)")
    return f"/uploads/{key}"


def delete_photos_for_user(user_id):
    """Delete all photos for a user from R2/local storage."""
    from models import TaskSolution
    solutions = TaskSolution.query.filter_by(user_id=user_id).filter(
        TaskSolution.original_photo_url.isnot(None)
    ).all()

    deleted = 0
    for sol in solutions:
        url = sol.original_photo_url or ''
        try:
            if _r2_configured() and R2_PUBLIC_URL and url.startswith(R2_PUBLIC_URL):
                key = url.replace(R2_PUBLIC_URL.rstrip('/') + '/', '')
                _delete_from_r2(key)
                deleted += 1
            elif url.startswith('/uploads/'):
                filepath = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    url.lstrip('/')
                )
                if os.path.exists(filepath):
                    os.remove(filepath)
                    deleted += 1
        except Exception as e:
            logger.warning(f"Failed to delete photo {url}: {e}")

    logger.info(f"Deleted {deleted} photos for user {user_id}")
    return deleted


def delete_all_solutions(user_id):
    """Delete all TaskSolution records and their photos for a user."""
    deleted_photos = delete_photos_for_user(user_id)

    from models import db, TaskSolution
    count = TaskSolution.query.filter_by(user_id=user_id).delete()
    db.session.commit()

    logger.info(f"Deleted {count} TaskSolution records for user {user_id} ({deleted_photos} photos)")
    return count


def _delete_from_r2(key):
    """Delete a single object from R2."""
    try:
        import boto3
        from botocore.config import Config

        endpoint_url = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        s3 = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )
        s3.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
        logger.info(f"Deleted from R2: {key}")
    except Exception as e:
        logger.error(f"R2 delete failed for {key}: {e}")
        raise


def get_photo_dimensions(photo_bytes):
    """
    Get image dimensions (width, height) from bytes.
    Returns (width, height) or (0, 0) if unable to determine.
    """
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(photo_bytes))
        return img.size  # (width, height)
    except Exception:
        pass

    # Fallback: try to parse JPEG header
    try:
        if photo_bytes[:2] == b'\xff\xd8':  # JPEG
            # Simple SOF0 marker search
            i = 2
            while i < len(photo_bytes) - 8:
                if photo_bytes[i] == 0xFF and photo_bytes[i + 1] in (0xC0, 0xC2):
                    height = (photo_bytes[i + 5] << 8) + photo_bytes[i + 6]
                    width = (photo_bytes[i + 7] << 8) + photo_bytes[i + 8]
                    return (width, height)
                i += 1
    except Exception:
        pass

    return (0, 0)
