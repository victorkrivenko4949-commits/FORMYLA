# -*- coding: utf-8 -*-
"""
wb_ws.py — WebSocket signalling for videoconference (Flask-SocketIO).

Заменяет HTTP polling (wb_call.py) на событийную WebSocket-модель.
Все обработчики зарегистрированы на namespace "/ws-call".

WebSocket события (клиент -> сервер):
  join          {room, name, user_id?}      -> {ok, peer_id, participants, role, flags}
  signal        {to, type, data}            -> пересылается адресату
  leave         {}                          -> уведомление остальным
  mute          {target?, kind}             -> mute своего/чужого микрофона/камеры
  kick          {target}                    -> удалить участника
  role-change   {target, role}              -> изменить роль
  chat-msg      {text, to?}                -> сообщение чата
  reaction      {type, emoji?}             -> эмодзи-реакция
  hand-raise    {on}                        -> поднять/опустить руку
  screen-share  {action}                    -> 'start' | 'stop'
  pin           {target?}                   -> закрепить участника
  set-flag      {flag, value}               -> установить флаг комнаты

WebSocket события (сервер -> клиент):
  participant-joined  {peer_id, name, role, ...}
  participant-left    {peer_id}
  signal              {from, type, data}
  mute-changed        {target, kind, state}
  kicked              {}
  role-changed        {target, role}
  chat-msg            {from, name, text, to?}
  reaction            {from, type, emoji?}
  hand-raise          {peer_id, on}
  screen-share        {peer_id, action}
  host-changed        {peer_id}
  flag-changed        {flag, value}
  room-state          {participants, flags, ...}
  error               {message}
"""

from __future__ import annotations

import logging
import threading
import time
import uuid

from flask import request
from flask_socketio import SocketIO, emit, join_room as sio_join_room, \
    leave_room as sio_leave_room, close_room

from routes.room_state import (
    ROLE_HOST, ROLE_CO_HOST, ROLE_PARTICIPANT,
    get_room, join_or_create_room, leave_room,
    change_role, kick_participant, set_flag,
    has_permission, _gc as room_gc,
)

logger = logging.getLogger(__name__)

# Глобальный экземпляр SocketIO (инициализируется в app.py)
socketio: SocketIO = None  # type: ignore

# Namespace для всех звонков
WS_NAMESPACE = "/ws-call"


def init_socketio(app, **kwargs):
    """Инициализировать SocketIO и зарегистрировать обработчики."""
    global socketio
    from flask_socketio import SocketIO as _SI
    socketio = _SI(app, **kwargs)

    # GC для stale-комнат (каждые 5 минут)
    _gc_timer = threading.Timer(300, _gc_loop)
    _gc_timer.daemon = True
    _gc_timer.start()

    _register_handlers()
    logger.info("[ws] SocketIO initialized on namespace %s", WS_NAMESPACE)
    return socketio


def _gc_loop():
    """Периодическая очистка stale-комнат."""
    while True:
        try:
            room_gc()
        except Exception:
            logger.exception("[ws] GC error")
        threading.Event().wait(300)


def _register_handlers():
    """Зарегистрировать все WebSocket event handlers на namespace /ws-call."""

    @socketio.on("connect", namespace=WS_NAMESPACE)
    def on_connect():
        logger.info("[ws] connect sid=%s", request.sid)

    @socketio.on("disconnect", namespace=WS_NAMESPACE)
    def on_disconnect():
        sid = request.sid
        logger.info("[ws] disconnect sid=%s", sid)
        # Найти комнату, в которой был этот sid, и выйти
        from routes.room_state import _ROOMS, _LOCK
        with _LOCK:
            for room_id, room in dict(_ROOMS).items():
                peer_id = room.sid_to_peer.get(sid)
                if peer_id is not None:
                    break
            else:
                return  # sid не найден ни в одной комнате
        # Выходим из комнаты вне блокировки (leave_room сама берёт _LOCK)
        result = leave_room(room_id, sid)
        if result is not None:
            # Уведомить остальных
            _broadcast(room_id, "participant-left", {
                "peer_id": peer_id,
            }, skip_sid=sid)
        sio_leave_room(room_id, namespace=WS_NAMESPACE)

    @socketio.on("join", namespace=WS_NAMESPACE)
    def on_join(data):
        sid = request.sid
        room_id = _normalize_room(data.get("room", ""))
        name = (data.get("name") or "Участник").strip()[:32]
        user_id = data.get("user_id")

        if not room_id:
            emit("error", {"message": "bad_room"}, namespace=WS_NAMESPACE)
            return

        peer_id = uuid.uuid4().hex[:12]

        # Атомарная операция: создать комнату или присоединиться
        status = join_or_create_room(room_id, sid, peer_id, name, user_id)

        if status == "created":
            sio_join_room(room_id, namespace=WS_NAMESPACE)
            room = get_room(room_id)
            emit("joined", {
                "ok": True,
                "peer_id": peer_id,
                "role": ROLE_HOST,
                "participants": [p.to_dict() for p in room.participants.values()] if room else [],
                "flags": dict(room.flags) if room else {},
            }, namespace=WS_NAMESPACE)
            logger.info("[ws] room created room=%s host=%s peer=%s", room_id, peer_id, name)

        elif status == "joined":
            sio_join_room(room_id, namespace=WS_NAMESPACE)
            room = get_room(room_id)
            emit("joined", {
                "ok": True,
                "peer_id": peer_id,
                "role": ROLE_PARTICIPANT,
                "participants": [p.to_dict() for p in room.participants.values()] if room else [],
                "flags": dict(room.flags) if room else {},
            }, namespace=WS_NAMESPACE)
            _broadcast(room_id, "participant-joined", {
                "peer_id": peer_id,
                "name": name,
                "role": ROLE_PARTICIPANT,
                "mic_on": True,
                "cam_on": True,
                "hand_raised": False,
                "screen_sharing": False,
            }, skip_sid=sid)
            logger.info("[ws] join room=%s peer=%s name=%s", room_id, peer_id, name)

        elif status == "locked":
            emit("error", {"message": "room_locked"}, namespace=WS_NAMESPACE)

        elif status == "full":
            emit("error", {"message": "room_full_or_not_found"}, namespace=WS_NAMESPACE)

        elif status == "waiting":
            emit("waiting", {"message": "host will let you in soon"}, namespace=WS_NAMESPACE)
            _broadcast(room_id, "waiting-request", {
                "name": name,
            })

    @socketio.on("signal", namespace=WS_NAMESPACE)
    def on_signal(data):
        """Пересылка WebRTC signalling (offer/answer/ICE)."""
        sid = request.sid
        room_id = _find_room_by_sid(sid)
        if not room_id:
            return
        to_peer = data.get("to")
        if not to_peer:
            return
        # Найти sid получателя
        room = get_room(room_id)
        if room is None:
            return
        target = room.get_participant_by_peer(to_peer)
        if target is None:
            return
        # Переслать сигнал только адресату
        _send_to_sid(target.sid, "signal", {
            "from": room.sid_to_peer.get(sid),
            "type": data.get("type"),       # 'offer' | 'answer' | 'ice'
            "data": data.get("data"),
        })

    @socketio.on("leave", namespace=WS_NAMESPACE)
    def on_leave():
        sid = request.sid
        room_id = _find_room_by_sid(sid)
        if not room_id:
            return
        room = get_room(room_id)
        if room is None:
            return
        peer_id = room.sid_to_peer.get(sid)
        result = leave_room(room_id, sid)
        sio_leave_room(room_id, namespace=WS_NAMESPACE)
        if result is not None:
            _broadcast(room_id, "participant-left", {
                "peer_id": peer_id,
            }, skip_sid=sid)
        elif room_id:
            # Комната удалена (все ушли)
            _broadcast(room_id, "room-ended", {})
            close_room(room_id, namespace=WS_NAMESPACE)

    @socketio.on("mute", namespace=WS_NAMESPACE)
    def on_mute(data):
        """Заглушить микрофон/камеру (своего или чужого участника)."""
        sid = request.sid
        room_id = _find_room_by_sid(sid)
        if not room_id:
            return
        room = get_room(room_id)
        if room is None:
            return
        actor = room.get_participant_by_sid(sid)
        if actor is None:
            return
        kind = data.get("kind", "mic")  # 'mic' | 'cam'
        target_peer = data.get("target")

        if target_peer and target_peer != actor.peer_id:
            # Попытка заглушить другого — нужны права
            if not has_permission(actor.role, "mute_other_mic" if kind == "mic" else "mute_other_cam"):
                emit("error", {"message": "no_permission"}, namespace=WS_NAMESPACE)
                return
            target = room.get_participant_by_peer(target_peer)
            if target is None:
                return
            if kind == "mic":
                target.mic_on = False
            else:
                target.cam_on = False
            _send_to_sid(target.sid, "mute-changed", {
                "target": target_peer,
                "kind": kind,
                "state": False,
            })
            _broadcast(room_id, "mute-changed", {
                "target": target_peer,
                "kind": kind,
                "state": False,
            }, skip_sid=target.sid)
        else:
            # Заглушить себя
            state = data.get("state", False)
            if kind == "mic":
                actor.mic_on = not state  # state=True означает muted
            else:
                actor.cam_on = not state
            _broadcast(room_id, "mute-changed", {
                "target": actor.peer_id,
                "kind": kind,
                "state": state,
            })

    @socketio.on("kick", namespace=WS_NAMESPACE)
    def on_kick(data):
        sid = request.sid
        room_id = _find_room_by_sid(sid)
        if not room_id:
            return
        target_peer = data.get("target")
        if not target_peer:
            return
        target_sid = kick_participant(room_id, sid, target_peer)
        if target_sid:
            _send_to_sid(target_sid, "kicked", {})
            sio_leave_room(target_sid, room_id, namespace=WS_NAMESPACE)
            _broadcast(room_id, "participant-left", {
                "peer_id": target_peer,
            }, skip_sid=target_sid)

    @socketio.on("role-change", namespace=WS_NAMESPACE)
    def on_role_change(data):
        sid = request.sid
        room_id = _find_room_by_sid(sid)
        if not room_id:
            return
        target = data.get("target")
        new_role = data.get("role")
        if not target or new_role not in (ROLE_CO_HOST, ROLE_PARTICIPANT, ROLE_HOST):
            return
        ok = change_role(room_id, sid, target, new_role)
        if ok:
            _broadcast(room_id, "role-changed", {
                "target": target,
                "role": new_role,
            })
            if new_role == ROLE_HOST:
                _broadcast(room_id, "host-changed", {
                    "peer_id": target,
                })
        else:
            emit("error", {"message": "role_change_failed"}, namespace=WS_NAMESPACE)

    @socketio.on("chat-msg", namespace=WS_NAMESPACE)
    def on_chat_msg(data):
        sid = request.sid
        room_id = _find_room_by_sid(sid)
        if not room_id:
            return
        room = get_room(room_id)
        if room is None:
            return
        actor = room.get_participant_by_sid(sid)
        if actor is None:
            return
        text = (data.get("text") or "").strip()[:1000]
        if not text:
            return
        to_peer = data.get("to")  # None = общий чат
        if to_peer:
            # Личное сообщение
            target = room.get_participant_by_peer(to_peer)
            if target:
                _send_to_sid(target.sid, "chat-msg", {
                    "from": actor.peer_id,
                    "name": actor.name,
                    "text": text,
                    "to": to_peer,
                })
                _send_to_sid(sid, "chat-msg", {
                    "from": actor.peer_id,
                    "name": actor.name,
                    "text": text,
                    "to": to_peer,
                })
        else:
            # Общий чат
            _broadcast(room_id, "chat-msg", {
                "from": actor.peer_id,
                "name": actor.name,
                "text": text,
            })

    @socketio.on("reaction", namespace=WS_NAMESPACE)
    def on_reaction(data):
        sid = request.sid
        room_id = _find_room_by_sid(sid)
        if not room_id:
            return
        room = get_room(room_id)
        if room is None:
            return
        actor = room.get_participant_by_sid(sid)
        if actor is None:
            return
        _broadcast(room_id, "reaction", {
            "from": actor.peer_id,
            "type": data.get("type", "emoji"),
            "emoji": data.get("emoji", "👍"),
        })

    @socketio.on("hand-raise", namespace=WS_NAMESPACE)
    def on_hand_raise(data):
        sid = request.sid
        room_id = _find_room_by_sid(sid)
        if not room_id:
            return
        room = get_room(room_id)
        if room is None:
            return
        actor = room.get_participant_by_sid(sid)
        if actor is None:
            return
        on = bool(data.get("on", False))
        actor.hand_raised = on
        _broadcast(room_id, "hand-raise", {
            "peer_id": actor.peer_id,
            "on": on,
        })

    @socketio.on("screen-share", namespace=WS_NAMESPACE)
    def on_screen_share(data):
        sid = request.sid
        room_id = _find_room_by_sid(sid)
        if not room_id:
            return
        room = get_room(room_id)
        if room is None:
            return
        actor = room.get_participant_by_sid(sid)
        if actor is None:
            return
        action = data.get("action", "stop")
        if action == "start":
            actor.screen_sharing = True
        else:
            actor.screen_sharing = False
        _broadcast(room_id, "screen-share", {
            "peer_id": actor.peer_id,
            "action": action,
        })

    @socketio.on("set-flag", namespace=WS_NAMESPACE)
    def on_set_flag(data):
        sid = request.sid
        room_id = _find_room_by_sid(sid)
        if not room_id:
            return
        flag = data.get("flag")
        value = bool(data.get("value", False))
        ok = set_flag(room_id, sid, flag, value)
        if ok:
            _broadcast(room_id, "flag-changed", {
                "flag": flag,
                "value": value,
            })

    @socketio.on("get-room-state", namespace=WS_NAMESPACE)
    def on_get_room_state():
        sid = request.sid
        room_id = _find_room_by_sid(sid)
        if not room_id:
            return
        room = get_room(room_id)
        if room is None:
            return
        emit("room-state", {
            "participants": [p.to_dict() for p in room.participants.values()],
            "flags": dict(room.flags),
        }, namespace=WS_NAMESPACE)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_room(raw: str) -> str:
    """Очистить и нормализовать ID комнаты."""
    if not isinstance(raw, str):
        return ""
    s = raw.strip()[:64]
    return "".join(c for c in s if c.isalnum() or c in ("-", "_"))


def _find_room_by_sid(sid: str):
    """Найти room_id по SocketIO session id."""
    from routes.room_state import _ROOMS, _LOCK
    with _LOCK:
        for room_id, room in _ROOMS.items():
            if sid in room.sid_to_peer:
                return room_id
    return None


def _broadcast(room_id: str, event: str, data: dict, skip_sid: str = None):
    """Отправить событие всем в комнате, опционально пропуская отправителя."""
    if skip_sid:
        emit(event, data, room=room_id, skip_sid=skip_sid, namespace=WS_NAMESPACE)
    else:
        emit(event, data, room=room_id, namespace=WS_NAMESPACE)


def _send_to_sid(sid: str, event: str, data: dict):
    """Отправить событие конкретному sid."""
    emit(event, data, to=sid, namespace=WS_NAMESPACE)
