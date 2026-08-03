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

JWT is generated with the standard library only (no PyJWT dependency).  The
spec we implement is LiveKit's documented token shape:

    header  = { "alg": "HS256", "typ": "JWT" }
    payload = {
        "iss": <api_key>,
        "sub": <identity>,
        "name": <display name>,
        "nbf": now,
        "iat": now,
        "exp": now + 60*60,                  # 1 hour
        "video": {
            "room":      <room>,
            "roomJoin":  True,
            "canPublish": True,
            "canSubscribe": True,
            "canPublishData": True
        }
    }
    sig = HMAC_SHA256( base64url(header) + "." + base64url(payload), secret )
    token = base64url(header) + "." + base64url(payload) + "." + base64url(sig)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
import uuid

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

wb_meet_bp = Blueprint("wb_meet", __name__, url_prefix="/api/wb_meet")

# How long each issued token stays valid.  LiveKit lets clients reconnect
# transparently while the JWT is still good; one hour is plenty for a
# tutoring session and keeps the blast radius small if a token leaks.
TOKEN_TTL_SECONDS = 60 * 60

# Soft cap on participants per room — enforced at token-issue time.  LiveKit
# itself has no built-in "max participants" config in the free Cloud plan;
# we just refuse to mint more tokens once the limit is reached.
MAX_PARTICIPANTS_PER_ROOM = 10

# In-memory bookkeeping: room_id -> set(identities).  Resets on process
# restart;  that is fine — the real source of truth is the LiveKit server,
# and we only use this to enforce the 10-person cap on our side.
_ROOM_COUNTS: dict[str, set[str]] = {}
import threading
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
        "nbf": now,
        "iat": now,
        "exp": now + int(ttl_seconds),
        "jti": uuid.uuid4().hex,
        # LiveKit-specific "video grant" — what the participant is allowed to do.
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
    s_b = _b64url(sig)
    return f"{h_b}.{p_b}.{s_b}"


# Allow ASCII letters, digits, dash, underscore.  Same rules as the 1-to-1
# call blueprint so a room code works in both UIs interchangeably.
_ROOM_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_NAME_RE = re.compile(r"^[\w\u00A0-\uFFFF .,\-']{1,40}$", re.UNICODE)


@wb_meet_bp.route("/config", methods=["GET"])
def config():
    """Tiny endpoint the frontend uses to know whether the feature is wired up.

    Never reveals the API secret.  Returns:
      { enabled: true, url: "wss://...", max: 10 }   if env is set
      { enabled: false, reason: "..." }              otherwise
    """
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
    })


@wb_meet_bp.route("/token", methods=["POST"])
def token():
    """Issue a LiveKit access JWT for joining {room} as {name}.

    Request JSON:
        { "room": "math-42", "name": "Виктор" }

    Response JSON (200):
        { "token": "<jwt>", "url": "wss://...", "identity": "...", "room": "..." }

    Errors:
        503  feature not configured on the server
        400  bad / missing arguments
        409  room is full (>= MAX_PARTICIPANTS_PER_ROOM)
    """
    env = _env()
    if not env:
        return jsonify({"error": "not_configured"}), 503
    url, api_key, api_secret = env

    data = request.get_json(silent=True) or {}
    room = (data.get("room") or "").strip()
    name = (data.get("name") or "").strip() or "Гость"

    if not _ROOM_RE.match(room):
        return jsonify({"error": "bad_room",
                        "hint": "Use 1-64 chars of A-Z, a-z, 0-9, - or _"}), 400
    if not _NAME_RE.match(name):
        # Soft-reject so users with weird unicode names still work.
        name = "Гость"

    identity = uuid.uuid4().hex[:12]

    # Enforce participant cap on our side (LiveKit free tier doesn't expose
    # this as a server-side setting).
    with _LOCK:
        members = _ROOM_COUNTS.setdefault(room, set())
        if len(members) >= MAX_PARTICIPANTS_PER_ROOM:
            return jsonify({
                "error": "room_full",
                "limit": MAX_PARTICIPANTS_PER_ROOM,
            }), 409
        members.add(identity)

    try:
        jwt_token = _make_token(
            api_key, api_secret,
            identity=identity, name=name, room=room,
        )
    except Exception as exc:
        logger.exception("[wb_meet] token error: %s", exc)
        with _LOCK:
            _ROOM_COUNTS.get(room, set()).discard(identity)
        return jsonify({"error": "token_error"}), 500

    logger.info("[wb_meet] token issued room=%s identity=%s name=%s", room, identity, name)
    return jsonify({
        "token": jwt_token,
        "url": url,
        "identity": identity,
        "name": name,
        "room": room,
        "ttl": TOKEN_TTL_SECONDS,
    })


@wb_meet_bp.route("/release", methods=["POST"])
def release():
    """Frontend calls this when the user leaves the room — frees one slot.

    LiveKit will also drop them from its side, but our local counter needs
    to be updated explicitly because we don't listen to webhooks here.
    """
    data = request.get_json(silent=True) or {}
    room = (data.get("room") or "").strip()
    identity = (data.get("identity") or "").strip()
    if not room or not identity:
        return jsonify({"error": "bad_args"}), 400
    with _LOCK:
        members = _ROOM_COUNTS.get(room)
        if members:
            members.discard(identity)
            if not members:
                _ROOM_COUNTS.pop(room, None)
    return jsonify({"ok": True})


@wb_meet_bp.route("/status", methods=["GET"])
def status():
    """Lightweight debug endpoint."""
    env = _env()
    with _LOCK:
        rooms = {r: len(s) for r, s in _ROOM_COUNTS.items()}
    return jsonify({
        "configured": bool(env),
        "rooms": rooms,
        "limit": MAX_PARTICIPANTS_PER_ROOM,
    })
