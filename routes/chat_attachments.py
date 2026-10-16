# -*- coding: utf-8 -*-
"""
routes/chat_attachments.py — CHAT_DOCS_V1 (15.10.2026)

Дополнение к чату (личному и групповому) БЕЗ правки app.py / chat.html / group_chat.html
(файлы слишком большие для безопасной правки). Регистрируется автоматически из
routes/__init__.py по той же схеме, что PWA и каталог олимпиад.

Что делает:
  1. POST /api/chat/<friend_id>/upload-file  и  POST /api/groups/<group_id>/upload-file —
     загрузка вложений: фото (до 20 МБ, раньше 5), видео (до 50 МБ) и ДОКУМЕНТЫ
     (PDF, Word, Excel, PowerPoint, TXT, RTF, ODT/ODS/ODP, CSV, ZIP/RAR/7z).
     Файл сохраняется в static/uploads/chat/<user_id>/ — ровно туда, где его ждёт
     проверка владельца в api_chat_send / api_groups_send.
     Фото без расширения (вставка из буфера, часть Android-галерей) получают расширение
     из MIME-типа вместо ошибки 400 — это и была «ошибка при отправке фото».
     Документы отдаются с kind='pdf': существующий сервер принимает только
     image/pdf/video, а карточка «pdf» в чате — это универсальная карточка файла
     (иконка + имя + размер + скачать).
  2. after_request: на страницах чата подключает static/css/chat_overrides.css и
     static/js/chat_overrides.js (убирают кнопку «Поделиться задачей», уменьшают
     контекстное меню сообщения в 2 раза, переключают загрузку на новый роут).

Отключить: CHAT_ATTACHMENTS_AUTOREG=0.
"""
from __future__ import annotations

import logging
import os
import uuid

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

logger = logging.getLogger(__name__)

chat_attachments_bp = Blueprint("chat_attachments", __name__)

ASSET_VERSION = "1"

ALLOWED_IMG = {"jpg", "jpeg", "png", "webp", "gif", "bmp"}
ALLOWED_PDF = {"pdf"}
ALLOWED_DOC = {"doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "rtf",
               "odt", "ods", "odp", "csv", "zip", "rar", "7z"}
ALLOWED_VIDEO = {"mp4", "webm", "mov", "m4v", "ogg"}
MAX_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024

_ERR_TYPE = ("Разрешены изображения (jpg/png/webp/gif), видео (mp4/webm/mov) и документы "
             "(PDF, Word, Excel, PowerPoint, TXT, ZIP)")


def _ext_and_name(f):
    """Расширение файла; если его нет — берём из MIME (фикс фото из буфера обмена)."""
    original_name = os.path.basename(f.filename or "")[:255]
    ext = (original_name.rsplit(".", 1)[-1] if "." in original_name else "").lower()
    if ext not in (ALLOWED_IMG | ALLOWED_PDF | ALLOWED_DOC | ALLOWED_VIDEO):
        mt = (f.mimetype or "").lower()
        if mt.startswith("image/"):
            ext = mt.split("/", 1)[1].replace("jpeg", "jpg")
            ext = ext if ext in ALLOWED_IMG else "png"
            original_name = f"photo.{ext}"
        elif mt.startswith("video/"):
            ext = "mp4"
            original_name = "video.mp4"
        elif mt == "application/pdf":
            ext = "pdf"
            original_name = original_name or "document.pdf"
    return ext, original_name


def _save_upload():
    f = request.files.get("file")
    if f is None:
        return jsonify({"error": "Файл не передан"}), 400

    ext, original_name = _ext_and_name(f)
    if ext in ALLOWED_IMG:
        att_kind = "image"
    elif ext in ALLOWED_PDF:
        att_kind = "pdf"
    elif ext in ALLOWED_DOC:
        att_kind = "pdf"   # универсальная карточка файла в текущем фронтенде/бэкенде
    elif ext in ALLOWED_VIDEO:
        att_kind = "video"
    else:
        return jsonify({"error": _ERR_TYPE}), 400

    f.stream.seek(0, os.SEEK_END)
    size = f.stream.tell()
    f.stream.seek(0)
    if size <= 0:
        return jsonify({"error": "Файл пустой"}), 400
    size_limit = MAX_VIDEO_BYTES if att_kind == "video" else MAX_BYTES
    if size > size_limit:
        return jsonify({"error": f"Файл больше {size_limit // (1024 * 1024)} МБ"}), 400

    rel_folder = os.path.join("static", "uploads", "chat", str(current_user.id))
    abs_folder = os.path.join(current_app.root_path, rel_folder)
    os.makedirs(abs_folder, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.{ext}"
    f.save(os.path.join(abs_folder, fname))

    url = f"/static/uploads/chat/{current_user.id}/{fname}"
    return jsonify({
        "success": True,
        "attachment": {"url": url, "kind": att_kind, "name": original_name, "size": size},
    })


def _is_friend(friend_id: int) -> bool:
    try:
        from models import Friendship  # noqa: WPS433
        uid = current_user.id
        q = Friendship.query.filter(
            ((Friendship.requester_id == uid) & (Friendship.addressee_id == friend_id)) |
            ((Friendship.requester_id == friend_id) & (Friendship.addressee_id == uid))
        ).first()
        return bool(q) and str(getattr(q, "status", "accepted")).lower() in ("accepted", "ok", "friends")
    except Exception as e:  # noqa: BLE001
        logger.warning("[chat_attachments] friendship check skipped: %r", e)
        return True


def _is_member(group_id: int) -> bool:
    try:
        from models import GroupMember  # noqa: WPS433
        return GroupMember.query.filter_by(group_id=group_id, user_id=current_user.id).first() is not None
    except Exception as e:  # noqa: BLE001
        logger.warning("[chat_attachments] membership check skipped: %r", e)
        return True


@chat_attachments_bp.route("/api/chat/<int:friend_id>/upload-file", methods=["POST"])
@login_required
def chat_upload_file(friend_id: int):
    if friend_id == current_user.id or not _is_friend(friend_id):
        return jsonify({"error": "Нет доступа к этому чату"}), 403
    return _save_upload()


@chat_attachments_bp.route("/api/groups/<int:group_id>/upload-file", methods=["POST"])
@login_required
def group_upload_file(group_id: int):
    if not _is_member(group_id):
        return jsonify({"error": "Вы не участник этой группы"}), 403
    return _save_upload()


_INJECT = (
    f'<link rel="stylesheet" href="/static/css/chat_overrides.css?v={ASSET_VERSION}">'
    f'<script src="/static/js/chat_overrides.js?v={ASSET_VERSION}" defer></script>'
)
_MARKERS = ('class="chat-wrapper"', 'class="gc-wrap"', 'id="chatFileInput"', 'id="gcFileInput"')


def install_chat_attachments(app) -> None:
    if getattr(app, "_chat_attachments_installed", False):
        return
    app._chat_attachments_installed = True

    if "chat_attachments" not in app.blueprints:
        # Регистрируем «оригинальным» register_blueprint, чтобы не зациклить автохук.
        try:
            from routes import _ORIG_REGISTER  # noqa: WPS433
            _ORIG_REGISTER(app, chat_attachments_bp)
        except Exception:  # noqa: BLE001
            app.register_blueprint(chat_attachments_bp)

    @app.after_request
    def _inject_chat_overrides(resp):
        try:
            if resp.direct_passthrough or resp.status_code != 200:
                return resp
            if "text/html" not in (resp.content_type or "").lower():
                return resp
            body = resp.get_data(as_text=True)
            if "chat_overrides.js" in body or "</body>" not in body:
                return resp
            if not any(m in body for m in _MARKERS):
                return resp
            resp.set_data(body.replace("</body>", _INJECT + "</body>", 1))
        except Exception:  # noqa: BLE001
            pass
        return resp

    logger.info("[BP] chat_attachments_bp registered (/api/chat/<id>/upload-file, /api/groups/<id>/upload-file)")
    print("[BP] chat_attachments_bp registered (/api/chat/<id>/upload-file, /api/groups/<id>/upload-file)")
