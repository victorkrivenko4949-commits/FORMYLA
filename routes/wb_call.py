# -*- coding: utf-8 -*-
"""
Blueprint  /api/wb_call/*
WebRTC 1-to-1 signalling for the whiteboard ("video meet").

Design notes
------------
* No SocketIO is added to the project.  The same Flask app + gunicorn workers
  serve everything;  the client polls /poll every ~1 s for incoming
  signalling messages (offer / answer / ICE candidate / peer-left).
* Rooms are kept in memory of a single Python process.  That matches a Render
  instance with the default ``--workers 1``.  If you ever scale to multiple
  gunicorn workers you must either (a) use sticky sessions per room id, or
  (b) move ROOMS into Redis.  A short comment is left next to the dict.
* Each room holds **at most 2** peers ("1-на-1, как договорились").
* Empty rooms are GC'd after ``ROOM_TTL_SECONDS`` of inactivity.

Endpoints
---------
    POST /api/wb_call/join     {room}                  -> {peer_id, peers:[other_ids], you}
    POST /api/wb_call/leave    {room, peer_id}         -> {ok: true}
    POST /api/wb_call/send     {room, from, to, msg}   -> {ok: true}
    POST /api/wb_call/poll     {room, peer_id}         -> {messages:[{from, msg}, ...]}

All endpoints return JSON.  No DB, no models.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from typing import Any, Deque, Dict, List

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

wb_call_bp = Blueprint("wb_call", __name__, url_prefix="/api/wb_call")

# ── In-memory store ───────────────────────────────────────────────────────────
# NOTE: single-process state.  Fine for default Render web service with 1 worker.
#       Move to Redis Pub/Sub if you ever spin up additional workers.
_LOCK = threading.RLock()
_ROOMS: Dict[str, "_Room"] = {}

# Очередь приглашений на видеозвонок для каждого user_id (получателя).
# Это in-memory pub/sub: отправитель кладёт сюда invite, получатель забирает
# через GET /api/wb_call/invites/poll и видит всплывающее уведомление.
# Список tuple'ов: (created_at, payload_dict). Чистится по TTL.
_INVITES: Dict[int, List[Any]] = {}
INVITE_TTL_SECONDS = 90             # приглашение «протухает» через 1.5 минуты
INVITE_MAX_PER_USER = 20            # safety cap чтобы не зафлудили

ROOM_TTL_SECONDS = 60 * 30          # 30 minutes of inactivity → drop the room
# PEER_TTL: основное значение — 90 секунд. Меньше — рискуем GC'нуть «живого»
# пира при кратковременных лагах polling'а. Больше — на стороне другого пира
# слишком долго висит «зомби», и партнёр получает 409 room_full при входе.
PEER_TTL_SECONDS = 90               # 1.5 минуты без poll → пир считается ушедшим
# Для случая «room_full»: делаем АГРЕССИВНУЮ переоценку — если пир не делал
# /poll дольше 15с, считаем его зомби и вычищаем перед отказом. Это закрывает
# самую частую проблему: пользователь обновил страницу, его старый peer ещё
# числится в комнате, и при повторном join ему отказывают.
STALE_PEER_THRESHOLD_FOR_JOIN = 15
MAX_PEERS_PER_ROOM = 2              # 1-на-1 call
MAX_QUEUE = 200                     # safety: discard old signalling msgs


class _Peer:
    __slots__ = ("id", "queue", "last_seen")

    def __init__(self, peer_id: str) -> None:
        self.id: str = peer_id
        self.queue: Deque[Dict[str, Any]] = deque(maxlen=MAX_QUEUE)
        self.last_seen: float = time.time()


class _Room:
    __slots__ = ("id", "peers", "created", "last_active")

    def __init__(self, room_id: str) -> None:
        self.id: str = room_id
        self.peers: Dict[str, _Peer] = {}
        self.created: float = time.time()
        self.last_active: float = time.time()


def _gc_locked() -> None:
    """Remove stale peers and empty rooms.  Caller must hold _LOCK."""
    now = time.time()
    to_drop_rooms: List[str] = []
    for rid, room in _ROOMS.items():
        # drop stale peers inside the room
        dead = [pid for pid, p in room.peers.items()
                if now - p.last_seen > PEER_TTL_SECONDS]
        for pid in dead:
            room.peers.pop(pid, None)
            # notify remaining peer(s)
            for other in room.peers.values():
                other.queue.append({"from": pid, "msg": {"type": "peer-left"}})
        if dead:
            room.last_active = now
        # drop the room if it has been empty for too long
        if not room.peers and now - room.last_active > ROOM_TTL_SECONDS:
            to_drop_rooms.append(rid)
    for rid in to_drop_rooms:
        _ROOMS.pop(rid, None)


def _normalize_room(raw: Any) -> str:
    """Restrict room ids to a safe printable subset."""
    if not isinstance(raw, str):
        return ""
    s = raw.strip()[:64]
    # keep ASCII letters, digits, dash, underscore
    return "".join(c for c in s if c.isalnum() or c in ("-", "_"))


# ── Endpoints ─────────────────────────────────────────────────────────────────
@wb_call_bp.route("/join", methods=["POST"])
def join():
    data = request.get_json(silent=True) or {}
    room_id = _normalize_room(data.get("room"))
    if not room_id:
        return jsonify({"error": "bad_room"}), 400

    with _LOCK:
        _gc_locked()
        room = _ROOMS.get(room_id)
        if room is None:
            room = _Room(room_id)
            _ROOMS[room_id] = room

        # Агрессивная очистка перед отказом «комната занята»: если в комнате
        # лимит достигнут, но кто-то из «занимающих» не делал /poll более
        # STALE_PEER_THRESHOLD_FOR_JOIN секунд — это зомби от предыдущей
        # вкладки/обновления страницы, его удаляем здесь же.
        if len(room.peers) >= MAX_PEERS_PER_ROOM:
            now = time.time()
            stale_pids = [
                pid for pid, p in room.peers.items()
                if now - p.last_seen > STALE_PEER_THRESHOLD_FOR_JOIN
            ]
            for pid in stale_pids:
                room.peers.pop(pid, None)
                for other in room.peers.values():
                    other.queue.append({"from": pid, "msg": {"type": "peer-left"}})
            if stale_pids:
                room.last_active = now
                logger.info(
                    "[wb_call] join: pruned %d stale peer(s) before slot check in room=%s",
                    len(stale_pids), room_id,
                )

        if len(room.peers) >= MAX_PEERS_PER_ROOM:
            return jsonify({
                "error": "room_full",
                "limit": MAX_PEERS_PER_ROOM,
            }), 409

        peer_id = uuid.uuid4().hex[:12]
        peer = _Peer(peer_id)
        room.peers[peer_id] = peer
        room.last_active = time.time()

        others = [pid for pid in room.peers.keys() if pid != peer_id]
        # let existing peers know somebody joined
        for pid in others:
            room.peers[pid].queue.append({
                "from": peer_id,
                "msg": {"type": "peer-joined"},
            })

    logger.info("[wb_call] join room=%s peer=%s others=%s", room_id, peer_id, others)
    return jsonify({
        "peer_id": peer_id,
        "you": peer_id,
        "peers": others,
        "room": room_id,
    })


@wb_call_bp.route("/leave", methods=["POST"])
def leave():
    data = request.get_json(silent=True) or {}
    room_id = _normalize_room(data.get("room"))
    peer_id = (data.get("peer_id") or "").strip()[:32]
    if not room_id or not peer_id:
        return jsonify({"error": "bad_args"}), 400

    with _LOCK:
        room = _ROOMS.get(room_id)
        if room and peer_id in room.peers:
            room.peers.pop(peer_id, None)
            for other in room.peers.values():
                other.queue.append({"from": peer_id, "msg": {"type": "peer-left"}})
            room.last_active = time.time()
    logger.info("[wb_call] leave room=%s peer=%s", room_id, peer_id)
    return jsonify({"ok": True})


@wb_call_bp.route("/send", methods=["POST"])
def send():
    """Push a signalling payload from `from` to `to` (both peer ids in the same room)."""
    data = request.get_json(silent=True) or {}
    room_id = _normalize_room(data.get("room"))
    from_id = (data.get("from") or "").strip()[:32]
    to_id = (data.get("to") or "").strip()[:32]
    msg = data.get("msg")
    if not room_id or not from_id or not to_id or not isinstance(msg, dict):
        return jsonify({"error": "bad_args"}), 400
    # Cap payload size — SDP/ICE are small;  hard cap so a misbehaving client
    # can't fill the queue with megabytes.
    try:
        if len(str(msg)) > 64 * 1024:
            return jsonify({"error": "payload_too_large"}), 413
    except Exception:
        pass

    with _LOCK:
        room = _ROOMS.get(room_id)
        if not room or to_id not in room.peers:
            return jsonify({"error": "peer_not_found"}), 404
        room.peers[to_id].queue.append({"from": from_id, "msg": msg})
        # mark sender alive too
        if from_id in room.peers:
            room.peers[from_id].last_seen = time.time()
        room.last_active = time.time()
    return jsonify({"ok": True})


@wb_call_bp.route("/poll", methods=["POST"])
def poll():
    """Drain the queue for this peer.  Returns immediately (short poll)."""
    data = request.get_json(silent=True) or {}
    room_id = _normalize_room(data.get("room"))
    peer_id = (data.get("peer_id") or "").strip()[:32]
    if not room_id or not peer_id:
        return jsonify({"error": "bad_args"}), 400

    with _LOCK:
        _gc_locked()
        room = _ROOMS.get(room_id)
        if not room or peer_id not in room.peers:
            return jsonify({"error": "peer_not_found", "messages": []}), 404
        peer = room.peers[peer_id]
        peer.last_seen = time.time()
        messages = list(peer.queue)
        peer.queue.clear()
        # caller might also want to know about current peers (e.g. for late joiners
        # whose initial "peers" list missed a recent join)
        peers = [pid for pid in room.peers.keys() if pid != peer_id]
        room.last_active = time.time()
    return jsonify({"messages": messages, "peers": peers})


@wb_call_bp.route("/status", methods=["GET"])
def status():
    """Lightweight debug endpoint: how many rooms / peers in memory."""
    with _LOCK:
        _gc_locked()
        rooms_summary = [
            {"id": rid, "peers": len(r.peers)}
            for rid, r in _ROOMS.items()
        ]
    return jsonify({
        "rooms": rooms_summary,
        "total_rooms": len(rooms_summary),
        "limits": {
            "max_peers_per_room": MAX_PEERS_PER_ROOM,
            "room_ttl_seconds": ROOM_TTL_SECONDS,
            "peer_ttl_seconds": PEER_TTL_SECONDS,
        },
    })


# ── Invitations (push-уведомления о звонке) ───────────────────────────────────
def _invites_gc_locked() -> None:
    """Удаляем протухшие invite'ы. Caller должен держать _LOCK."""
    now = time.time()
    for uid in list(_INVITES.keys()):
        fresh = [(ts, pl) for (ts, pl) in _INVITES[uid] if now - ts < INVITE_TTL_SECONDS]
        if fresh:
            _INVITES[uid] = fresh
        else:
            _INVITES.pop(uid, None)


@wb_call_bp.route("/invite", methods=["POST"])
def invite():
    """Отправить приглашение на звонок другому пользователю.

    POST body: { "friend_id": int, "room": "math-42" }
    Возвращает {ok: true} или 4xx с ошибкой.
    Получатель увидит всплывающее уведомление через /invites/poll.
    """
    try:
        from flask_login import current_user
        from models import db, User, Friendship  # noqa: F401
    except Exception as e:
        logger.warning("[wb_call] /invite import err: %s", e)
        return jsonify({"error": "server_error"}), 500

    if not current_user.is_authenticated:
        return jsonify({"error": "auth_required"}), 401

    data = request.get_json(silent=True) or {}
    try:
        friend_id = int(data.get("friend_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "bad_friend_id"}), 400
    room_id = _normalize_room(data.get("room"))
    if not room_id:
        return jsonify({"error": "bad_room"}), 400
    if friend_id == current_user.id:
        return jsonify({"error": "cannot_invite_self"}), 400

    # Проверяем, что friend_id действительно друг (двусторонний accepted).
    try:
        is_friend = False
        if hasattr(current_user, "get_friends"):
            is_friend = any(f.id == friend_id for f in current_user.get_friends())
        if not is_friend:
            return jsonify({"error": "not_friends"}), 403
    except Exception as e:
        logger.warning("[wb_call] friend check err: %s", e)
        return jsonify({"error": "server_error"}), 500

    payload = {
        "from_id": current_user.id,
        "from_name": getattr(current_user, "nickname", None)
                     or getattr(current_user, "name", None)
                     or f"User #{current_user.id}",
        "from_avatar": getattr(current_user, "avatar_url", None),
        "room": room_id,
        "ts": int(time.time()),
    }

    with _LOCK:
        _invites_gc_locked()
        queue = _INVITES.setdefault(friend_id, [])
        # де-дуп: убираем предыдущие приглашения от того же отправителя в ту же комнату
        queue[:] = [
            (ts, pl) for (ts, pl) in queue
            if not (pl.get("from_id") == current_user.id and pl.get("room") == room_id)
        ]
        queue.append((time.time(), payload))
        if len(queue) > INVITE_MAX_PER_USER:
            queue[:] = queue[-INVITE_MAX_PER_USER:]

    logger.info("[wb_call] invite from=%s to=%s room=%s",
                current_user.id, friend_id, room_id)
    return jsonify({"ok": True})


@wb_call_bp.route("/invites/poll", methods=["GET"])
def invites_poll():
    """Получить активные приглашения текущего пользователя.

    Возвращает {invites: [{from_id, from_name, from_avatar, room, ts}, ...]}.
    Приглашения остаются в очереди до явного /invites/dismiss или TTL=90s.
    Клиент сам разбирается, какие он уже показывал (по from_id+room+ts).
    """
    try:
        from flask_login import current_user
    except Exception:
        return jsonify({"invites": []})

    if not current_user.is_authenticated:
        return jsonify({"invites": []})

    with _LOCK:
        _invites_gc_locked()
        queue = _INVITES.get(current_user.id, [])
        invites = [pl for (_ts, pl) in queue]
    return jsonify({"invites": invites})


@wb_call_bp.route("/invites/dismiss", methods=["POST"])
def invites_dismiss():
    """Удалить приглашение из очереди (после того как пользователь нажал
    Принять/Отклонить — чтобы оно не показывалось повторно после F5)."""
    try:
        from flask_login import current_user
    except Exception:
        return jsonify({"ok": True})

    if not current_user.is_authenticated:
        return jsonify({"ok": True})

    data = request.get_json(silent=True) or {}
    try:
        from_id = int(data.get("from_id"))
    except (TypeError, ValueError):
        from_id = None
    room = _normalize_room(data.get("room"))

    with _LOCK:
        queue = _INVITES.get(current_user.id)
        if queue:
            queue[:] = [
                (ts, pl) for (ts, pl) in queue
                if not (
                    (from_id is None or pl.get("from_id") == from_id) and
                    (not room or pl.get("room") == room)
                )
            ]
            if not queue:
                _INVITES.pop(current_user.id, None)
    return jsonify({"ok": True})
