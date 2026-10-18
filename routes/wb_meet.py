# -*- coding: utf-8 -*-
"""
Blueprint  /api/wb_meet/*
LiveKit-based group video meeting for the whiteboard ("up to 10 people").

This blueprint does **not** speak WebRTC itself.  It only mints short-lived
JWT access tokens that the browser uses to connect to a LiveKit server
(self-hosted or LiveKit Cloud).  All audio/video traffic flows between the
browser and the LiveKit SFU directly — our Flask app is never on that path.

ENV variables (Render -> Environment)
------------------------------------
    LIVEKIT_URL         e.g. "wss://your-project.livekit.cloud"
    LIVEKIT_API_KEY     e.g. "APIabc123..."
    LIVEKIT_API_SECRET  e.g. "abcdef0123456789..."

If any of these are missing the blueprint stays registered but every endpoint
returns 503 with a friendly explanation so the frontend can hide the button.

JWT is generated with the standard library only (no PyJWT dependency).

MEET_STABILITY_V1 (почему раньше «выкидывало»):
  * токен жил 1 час — после истечения LiveKit не давал переподключиться,
    и при любом обрыве сети участник вылетал.  Теперь TTL = 8 часов, а
    клиент при обрыве сам берёт свежий токен (см. static/js/wb_meet.js).
  * счётчик участников комнаты никогда не «протухал»: закрытая вкладка
    без /release занимала слот навсегда, и через несколько перезаходов
    комната отвечала 409 «заполнена».  Теперь слот живёт, пока клиент
    шлёт /heartbeat (раз в минуту); без heartbeat слот освобождается
    через SLOT_TTL_SECONDS.  Повторный вход с тем же identity не
    занимает второй слот.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import threading
import time
import uuid

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

wb_meet_bp = Blueprint("wb_meet", __name__, url_prefix="/api/wb_meet")

# How long each issued token stays valid.  LiveKit lets clients reconnect
# transparently only while the JWT is still good, so a long TTL is what
# keeps a 2-3 hour lesson from being "kicked".  The client also re-requests
# a token on every reconnect, so a leaked token is still low-risk.
TOKEN_TTL_SECONDS = 8 * 60 * 60

# Soft cap on participants per room — enforced at token-issue time.
MAX_PARTICIPANTS_PER_ROOM = 10

# A slot is considered abandoned if the browser hasn't pinged /heartbeat
# (or re-requested a token) for this long.
SLOT_TTL_SECONDS = 3 * 60

# In-memory bookkeeping: room_id -> { identity: last_seen_ts }.  Resets on
# process restart; that is fine — the real source of truth is LiveKit.
_ROOM_COUNTS: dict[str, dict[str, float]] = {}
_LOCK = threading.RLock()


def _env() -> tuple[str, str, str] | None:
    url = os.environ.get("LIVEKIT_URL", "").strip()
    key = os.environ.get("LIVEKIT_API_KEY", "").strip()
    sec = os.environ.get("LIVEKIT_API_SECRET", "").strip()
    if not (url and key and sec):
        return None
    return url, key, sec


def _b64url(data: bytes) -> str:
    """Base64-url encode without padding (per JWT spec / RFC 7515)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _make_token(api_key: str, api_secret: str, *,
                identity: str, name: str, room: str,
                ttl_seconds: int = TOKEN_TTL_SECONDS) -> str:
    """Build an HS256 LiveKit access JWT (no external dependencies)."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": api_key,
        "sub": identity,
        "name": name,
        "nbf": now - 10,            # небольшой запас на рассинхрон часов
        "iat": now,
        "exp": now + int(ttl_seconds),
        "jti": uuid.uuid4().hex,
        "video": {
            "room":            room,
            "roomJoin":        True,
            "canPublish":      True,
            "canSubscribe":    True,
            "canPublishData":  True,
        },
    }
    h_b = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b}.{p_b}".encode("ascii")
    sig = hmac.new(api_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h_b}.{p_b}.{_b64url(sig)}"


_ROOM_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_NAME_RE = re.compile(r"^[\w\u00A0-\uFFFF .,\-']{1,40}$", re.UNICODE)
_IDENT_RE = re.compile(r"^[a-f0-9]{12}$")


def _prune_locked(room: str) -> dict[str, float]:
    """Drop abandoned slots for `room`.  Caller must hold _LOCK."""
    members = _ROOM_COUNTS.setdefault(room, {})
    cutoff = time.time() - SLOT_TTL_SECONDS
    for ident in [i for i, ts in members.items() if ts < cutoff]:
        members.pop(ident, None)
    return members


@wb_meet_bp.route("/config", methods=["GET"])
def config():
    env = _env()
    if not env:
        return jsonify({
            "enabled": False,
            "reason": "LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET not configured on the server.",
        }), 200
    url, _key, _sec = env
    return jsonify({
        "enabled": True,
        "url": url,
        "max": MAX_PARTICIPANTS_PER_ROOM,
        "token_ttl_seconds": TOKEN_TTL_SECONDS,
        "heartbeat_seconds": 60,
    })


@wb_meet_bp.route("/token", methods=["POST"])
def token():
    """Issue a LiveKit access JWT for joining {room} as {name}.

    Request JSON:
        { "room": "math-42", "name": "Виктор", "identity": "<optional, for rejoin>" }

    Errors:
        503  feature not configured on the server
        400  bad / missing arguments
        409  room is full (>= MAX_PARTICIPANTS_PER_ROOM live slots)
    """
    env = _env()
    if not env:
        return jsonify({"error": "not_configured"}), 503
    url, api_key, api_secret = env

    data = request.get_json(silent=True) or {}
    room = (data.get("room") or "").strip()
    name = (data.get("name") or "").strip() or "Гость"
    prev_identity = (data.get("identity") or "").strip()

    if not _ROOM_RE.match(room):
        return jsonify({"error": "bad_room",
                        "hint": "Use 1-64 chars of A-Z, a-z, 0-9, - or _"}), 400
    if not _NAME_RE.match(name):
        name = "Гость"

    # Переподключение: тот же identity -> тот же слот, второй не занимаем.
    if prev_identity and _IDENT_RE.match(prev_identity):
        identity = prev_identity
    else:
        identity = uuid.uuid4().hex[:12]

    with _LOCK:
        members = _prune_locked(room)
        if identity not in members and len(members) >= MAX_PARTICIPANTS_PER_ROOM:
            return jsonify({
                "error": "room_full",
                "limit": MAX_PARTICIPANTS_PER_ROOM,
            }), 409
        members[identity] = time.time()

    try:
        jwt_token = _make_token(
            api_key, api_secret,
            identity=identity, name=name, room=room,
        )
    except Exception as exc:
        logger.exception("[wb_meet] token error: %s", exc)
        with _LOCK:
            _ROOM_COUNTS.get(room, {}).pop(identity, None)
        return jsonify({"error": "token_error"}), 500

    logger.info("[wb_meet] token issued room=%s identity=%s name=%s rejoin=%s",
                room, identity, name, bool(prev_identity))
    return jsonify({
        "token": jwt_token,
        "url": url,
        "identity": identity,
        "name": name,
        "room": room,
        "ttl": TOKEN_TTL_SECONDS,
    })


@wb_meet_bp.route("/heartbeat", methods=["POST"])
def heartbeat():
    """Browser pings this every ~60 s while in the call to keep its slot."""
    data = request.get_json(silent=True) or {}
    room = (data.get("room") or "").strip()
    identity = (data.get("identity") or "").strip()
    if not room or not identity:
        return jsonify({"error": "bad_args"}), 400
    with _LOCK:
        members = _prune_locked(room)
        members[identity] = time.time()
    return jsonify({"ok": True})


@wb_meet_bp.route("/release", methods=["POST"])
def release():
    """Frontend calls this when the user leaves the room — frees one slot."""
    data = request.get_json(silent=True) or {}
    room = (data.get("room") or "").strip()
    identity = (data.get("identity") or "").strip()
    if not room or not identity:
        return jsonify({"error": "bad_args"}), 400
    with _LOCK:
        members = _ROOM_COUNTS.get(room)
        if members:
            members.pop(identity, None)
            if not members:
                _ROOM_COUNTS.pop(room, None)
    return jsonify({"ok": True})


@wb_meet_bp.route("/status", methods=["GET"])
def status():
    """Lightweight debug endpoint."""
    env = _env()
    with _LOCK:
        rooms = {r: len(_prune_locked(r)) for r in list(_ROOM_COUNTS.keys())}
    return jsonify({
        "configured": bool(env),
        "rooms": rooms,
        "limit": MAX_PARTICIPANTS_PER_ROOM,
        "slot_ttl_seconds": SLOT_TTL_SECONDS,
        "token_ttl_seconds": TOKEN_TTL_SECONDS,
    })
