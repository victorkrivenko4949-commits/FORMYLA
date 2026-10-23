# -*- coding: utf-8 -*-
"""
Telegram Login Widget — server-side callback handler.

The widget posts (GET or POST) the user's Telegram identity together with an
HMAC-SHA256 hash signed by the bot's token. We verify the signature, look up
or create the matching User row, log them in via Flask-Login and redirect
either to /about?onboarding=1 (new user) or to /profile.

Docs: https://core.telegram.org/widgets/login
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import threading
import time
from datetime import datetime

from flask import Blueprint, abort, flash, jsonify, redirect, request, session, url_for
from flask_login import current_user, login_user

from models import User, db

log = logging.getLogger(__name__)

telegram_auth_bp = Blueprint("telegram_auth", __name__, url_prefix="/auth/telegram")


# ─────────────────────────── HMAC verification ───────────────────────────

# The auth_date freshness window (Telegram recommends 86400s = 24h).
_TELEGRAM_AUTH_TTL = 86400


def _bot_token() -> str:
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def _build_data_check_string(payload: dict) -> str:
    """Telegram requires `key=value` lines sorted alphabetically, joined by `\n`,
    EXCLUDING the `hash` field itself."""
    parts = []
    for key in sorted(payload.keys()):
        if key == "hash":
            continue
        value = payload[key]
        if value is None or value == "":
            continue
        parts.append(f"{key}={value}")
    return "\n".join(parts)


def verify_telegram_payload(payload: dict) -> bool:
    """Returns True if `payload` is signed by our bot token and is fresh."""
    token = _bot_token()
    if not token:
        log.error("TELEGRAM_BOT_TOKEN is not set — cannot verify payload")
        return False

    received_hash = payload.get("hash")
    if not received_hash:
        return False

    data_check_string = _build_data_check_string(payload)
    secret_key = hashlib.sha256(token.encode("utf-8")).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        return False

    # Freshness check
    try:
        auth_date = int(payload.get("auth_date", "0"))
    except (TypeError, ValueError):
        return False
    if auth_date <= 0 or (time.time() - auth_date) > _TELEGRAM_AUTH_TTL:
        return False

    return True


# ─────────────────────────── Routes ───────────────────────────

@telegram_auth_bp.route("/callback", methods=["GET", "POST"])
def telegram_callback():
    """Public callback for the Telegram Login Widget.

    Accepts both GET (default widget redirect mode) and POST (when using
    `data-onauth="onTelegramAuth(user)"` JS hook).
    """
    payload = request.values.to_dict(flat=True)  # merges GET + POST
    if not payload:
        flash("Не получены данные от Telegram", "error")
        return redirect(url_for("login"))

    if not verify_telegram_payload(payload):
        log.warning("Telegram login: invalid HMAC payload=%r", payload)
        flash("Не удалось проверить подпись Telegram. Попробуйте ещё раз.", "error")
        return redirect(url_for("login"))

    tg_id = str(payload.get("id", "")).strip()
    tg_username = (payload.get("username") or "").strip() or None
    tg_first = (payload.get("first_name") or "").strip()
    tg_last = (payload.get("last_name") or "").strip()
    tg_photo = (payload.get("photo_url") or "").strip() or None
    if not tg_id:
        flash("Некорректный ответ Telegram (нет id)", "error")
        return redirect(url_for("login"))

    is_new_user = False

    # 1) Если уже залогинены — привязка к текущему аккаунту
    if current_user.is_authenticated and getattr(current_user, "is_guest", False) is not True:
        # Проверим что этот telegram_id ещё ни к кому не привязан
        existing = User.query.filter_by(telegram_id=tg_id).first()
        if existing and existing.id != current_user.id:
            flash("Этот Telegram уже привязан к другому аккаунту.", "error")
            return redirect(url_for("profile"))
        current_user.telegram_id = tg_id
        current_user.telegram_username = tg_username
        if tg_photo and not getattr(current_user, "avatar_url", None):
            current_user.avatar_url = tg_photo
        db.session.commit()
        flash("Telegram успешно привязан к аккаунту!", "success")
        return redirect(url_for("profile"))

    # 2) Иначе — обычный вход / регистрация
    user = User.query.filter_by(telegram_id=tg_id).first()
    if user is None:
        # Регистрация нового пользователя без email (email можно добавить позже)
        synthetic_email = f"tg_{tg_id}@telegram.formyla.local"
        display_name = (tg_first + " " + tg_last).strip() or tg_username or f"tg_{tg_id}"
        user = User(
            email=synthetic_email,
            name=display_name,
            telegram_id=tg_id,
            telegram_username=tg_username,
            avatar_url=tg_photo,
            is_guest=False,
        )
        db.session.add(user)
        try:
            db.session.commit()
            is_new_user = True
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            log.exception("Telegram login: failed to create user: %s", exc)
            flash("Не удалось завершить регистрацию через Telegram.", "error")
            return redirect(url_for("login"))
    else:
        # Обновим username/photo если изменились
        changed = False
        if tg_username and user.telegram_username != tg_username:
            user.telegram_username = tg_username
            changed = True
        if tg_photo and not getattr(user, "avatar_url", None):
            user.avatar_url = tg_photo
            changed = True
        if changed:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

    user.last_login = datetime.utcnow()
    user.is_guest = False
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    session.permanent = True
    login_user(user, remember=True)

    # Welcome email — только если у пользователя есть реальный email
    if is_new_user and not (user.email or "").endswith("@telegram.formyla.local"):
        try:
            from services.email_service import send_welcome_email
            threading.Thread(target=send_welcome_email, args=(user,), daemon=True).start()
        except Exception as exc:
            log.warning("Welcome email failed (telegram): %s", exc)

    # Редирект для нового пользователя — на /intake
    if getattr(user, "onboarded_at", None) is None:
        return redirect(url_for("intake.intake_page"))
    return redirect(url_for("index"))


@telegram_auth_bp.route("/unlink", methods=["POST"])
def telegram_unlink():
    """Отвязать Telegram от текущего пользователя."""
    if not current_user.is_authenticated:
        return jsonify({"success": False, "error": "not_authenticated"}), 401
    current_user.telegram_id = None
    current_user.telegram_username = None
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500
    return jsonify({"success": True})
