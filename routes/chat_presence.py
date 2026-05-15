# -*- coding: utf-8 -*-
"""Chat presence blueprint (CHAT_PRESENCE_V1).

Endpoints
---------
GET  /api/chat/<friend_id>/presence
    JSON: {"online": bool, "last_seen": iso|null, "typing": bool}
POST /api/chat/<friend_id>/typing
    JSON body (optional): {"typing": true|false}; defaults to true.
    Stamps current_user's typing_to_id=friend_id, typing_at=now.

Auto-migration of the ``user_presence`` table happens at import time, so simply
registering this blueprint is enough.
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user

from models import db, UserPresence, Friendship


chat_presence_bp = Blueprint("chat_presence_bp", __name__)


# ---------- auto-migration ----------------------------------------------------

def _ensure_table() -> None:
    """Create user_presence table if absent. Idempotent."""
    try:
        from sqlalchemy import inspect as _inspect
        insp = _inspect(db.engine)
        if "user_presence" in insp.get_table_names():
            return
        UserPresence.__table__.create(bind=db.engine, checkfirst=True)
        print("[AUTO-MIGRATION] user_presence table created")
    except Exception as exc:  # pragma: no cover
        print("[AUTO-MIGRATION] user_presence failed: " + repr(exc))


# ---------- helpers -----------------------------------------------------------

def _are_friends(uid_a: int, uid_b: int) -> bool:
    if uid_a == uid_b:
        return False
    f = Friendship.query.filter(
        Friendship.status == "accepted",
        db.or_(
            db.and_(Friendship.user_id == uid_a, Friendship.friend_id == uid_b),
            db.and_(Friendship.user_id == uid_b, Friendship.friend_id == uid_a),
        ),
    ).first()
    return f is not None


def _get_or_create_presence(user_id: int) -> "UserPresence":
    row = UserPresence.query.get(user_id)
    if row is None:
        row = UserPresence(user_id=user_id, last_seen=datetime.utcnow())
        db.session.add(row)
    return row


def bump_last_seen(user_id: int) -> None:
    """Public helper: bump last_seen for *user_id*. Safe to call often."""
    try:
        row = _get_or_create_presence(user_id)
        row.last_seen = datetime.utcnow()
        db.session.commit()
    except Exception:
        db.session.rollback()


# ---------- routes ------------------------------------------------------------

@chat_presence_bp.route("/api/chat/<int:friend_id>/presence", methods=["GET"])
@login_required
def get_presence(friend_id: int):
    if not _are_friends(current_user.id, friend_id):
        return jsonify({"error": "not_friends"}), 403

    # Bump our own last_seen on every poll.
    bump_last_seen(current_user.id)

    row = UserPresence.query.get(friend_id)
    if row is None:
        return jsonify({"online": False, "last_seen": None, "typing": False})

    return jsonify({
        "online": row.is_online(),
        "last_seen": row.last_seen.isoformat() if row.last_seen else None,
        "typing": row.is_typing_to(current_user.id),
    })


@chat_presence_bp.route("/api/chat/<int:friend_id>/typing", methods=["POST"])
@login_required
def set_typing(friend_id: int):
    if not _are_friends(current_user.id, friend_id):
        return jsonify({"error": "not_friends"}), 403

    payload = request.get_json(silent=True) or {}
    is_typing = bool(payload.get("typing", True))

    try:
        row = _get_or_create_presence(current_user.id)
        row.last_seen = datetime.utcnow()
        if is_typing:
            row.typing_to_id = friend_id
            row.typing_at = datetime.utcnow()
        else:
            row.typing_to_id = None
            row.typing_at = None
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning("set_typing failed: %r", exc)
        return jsonify({"error": "db"}), 500

    return jsonify({"ok": True})
