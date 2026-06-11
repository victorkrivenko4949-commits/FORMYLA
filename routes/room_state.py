# -*- coding: utf-8 -*-
"""
room_state.py — Серверное состояние видеоконференции.

Хранит комнаты, участников, роли и флаги в памяти.
Используется WebSocket-хендлерами (wb_ws.py) для валидации прав.

Дизайн:
- Роли: 'host' (организатор), 'co-host' (со-организатор), 'participant'
- Права проверяются на сервере, не только на клиенте.
- Комнаты живут в памяти одного процесса (как wb_call.py).
- Если понадобятся несколько воркеров — перенести в Redis.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_ROOMS: Dict[str, "RoomState"] = {}

# Константы
ROOM_TTL_SECONDS = 60 * 60           # 1 час бездействия → дроп комнаты
PEER_TTL_SECONDS = 90                # 90с без poll/ping → пир считается ушедшим
MAX_PARTICIPANTS = 8
MAX_QUEUE = 200


# ── Роли и права ──────────────────────────────────────────────────────────────

ROLE_HOST = "host"
ROLE_CO_HOST = "co-host"
ROLE_PARTICIPANT = "participant"
ALL_ROLES = (ROLE_HOST, ROLE_CO_HOST, ROLE_PARTICIPANT)

# Какие роли имеют право на действие
_PERMISSIONS: Dict[str, set] = {
    "end_conference":    {ROLE_HOST},
    "kick":              {ROLE_HOST, ROLE_CO_HOST},
    "mute_other_mic":    {ROLE_HOST, ROLE_CO_HOST},
    "mute_other_cam":    {ROLE_HOST, ROLE_CO_HOST},
    "mute_all":          {ROLE_HOST, ROLE_CO_HOST},
    "mute_all_block":    {ROLE_HOST, ROLE_CO_HOST},
    "assign_co_host":    {ROLE_HOST},
    "transfer_host":     {ROLE_HOST},
    "manage_waiting":    {ROLE_HOST, ROLE_CO_HOST},
    "manage_recording":  {ROLE_HOST},    # co-host только если разрешено host
    "manage_breakout":   {ROLE_HOST, ROLE_CO_HOST},
    "spotlight":         {ROLE_HOST, ROLE_CO_HOST},
    "rename_participant": {ROLE_HOST},
    "pin_any":           {ROLE_HOST, ROLE_CO_HOST},
    "screen_share":      {ROLE_HOST, ROLE_CO_HOST, ROLE_PARTICIPANT},  # может быть ограничено host
}


def has_permission(role: str, action: str) -> bool:
    """Проверить, имеет ли роль право на действие."""
    allowed = _PERMISSIONS.get(action)
    if allowed is None:
        return False
    return role in allowed


# ── Модели ────────────────────────────────────────────────────────────────────

class Participant:
    __slots__ = (
        "sid", "peer_id", "user_id", "name", "role",
        "mic_on", "cam_on", "hand_raised", "screen_sharing",
        "joined_at", "last_active", "pinned", "spotlighted",
    )

    def __init__(self, sid: str, peer_id: str, name: str,
                 user_id: Optional[int] = None) -> None:
        self.sid: str = sid                     # SocketIO session id
        self.peer_id: str = peer_id             # уникальный id пира
        self.user_id: Optional[int] = user_id  # ID из БД (если авторизован)
        self.name: str = name
        self.role: str = ROLE_PARTICIPANT       # по умолчанию participant
        self.mic_on: bool = True
        self.cam_on: bool = True
        self.hand_raised: bool = False
        self.screen_sharing: bool = False
        self.joined_at: float = time.time()
        self.last_active: float = time.time()
        self.pinned: bool = False               # закреплён локально
        self.spotlighted: bool = False          # выделен для всех

    def to_dict(self) -> Dict[str, Any]:
        return {
            "peer_id": self.peer_id,
            "name": self.name,
            "role": self.role,
            "mic_on": self.mic_on,
            "cam_on": self.cam_on,
            "hand_raised": self.hand_raised,
            "screen_sharing": self.screen_sharing,
        }


class RoomState:
    __slots__ = (
        "id", "host_id", "participants", "sid_to_peer",
        "flags", "created_at", "last_active",
        "waiting_queue",
    )

    def __init__(self, room_id: str, host_sid: str, host_peer_id: str) -> None:
        self.id: str = room_id
        self.host_id: str = host_peer_id  # peer_id организатора
        self.participants: Dict[str, Participant] = {}  # peer_id -> Participant
        self.sid_to_peer: Dict[str, str] = {}           # sid -> peer_id
        self.flags: Dict[str, bool] = {
            "locked": False,
            "waiting_room": False,
            "mute_all_on_entry": False,
            "screen_share_only_host": False,
            "chat_allowed": True,
            "recording": False,
        }
        self.created_at: float = time.time()
        self.last_active: float = time.time()
        self.waiting_queue: List[Dict[str, Any]] = []

    def get_participant_by_sid(self, sid: str) -> Optional[Participant]:
        peer_id = self.sid_to_peer.get(sid)
        if peer_id is None:
            return None
        return self.participants.get(peer_id)

    def get_participant_by_peer(self, peer_id: str) -> Optional[Participant]:
        return self.participants.get(peer_id)

    @property
    def participant_count(self) -> int:
        return len(self.participants)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "host_id": self.host_id,
            "participant_count": self.participant_count,
            "flags": dict(self.flags),
        }


# ── API ───────────────────────────────────────────────────────────────────────

def create_room(room_id: str, host_sid: str, host_peer_id: str,
                host_name: str, user_id: Optional[int] = None) -> RoomState:
    """Создать новую комнату с организатором."""
    with _LOCK:
        room = RoomState(room_id, host_sid, host_peer_id)
        host = Participant(host_sid, host_peer_id, host_name, user_id)
        host.role = ROLE_HOST
        room.participants[host_peer_id] = host
        room.sid_to_peer[host_sid] = host_peer_id
        _ROOMS[room_id] = room
        logger.info("[room] created room=%s host=%s", room_id, host_peer_id)
        return room


def get_room(room_id: str) -> Optional[RoomState]:
    with _LOCK:
        return _ROOMS.get(room_id)


def join_room(room_id: str, sid: str, peer_id: str, name: str,
              user_id: Optional[int] = None) -> Optional[RoomState]:
    """Добавить участника в комнату. Возвращает None если комната не найдена."""
    with _LOCK:
        room = _ROOMS.get(room_id)
        if room is None:
            return None
        if len(room.participants) >= MAX_PARTICIPANTS:
            return None
        p = Participant(sid, peer_id, name, user_id)
        room.participants[peer_id] = p
        room.sid_to_peer[sid] = peer_id
        room.last_active = time.time()
        logger.info("[room] join room=%s peer=%s name=%s", room_id, peer_id, name)
        return room


def join_or_create_room(
    room_id: str, sid: str, peer_id: str, name: str,
    user_id: Optional[int] = None,
) -> str:
    """
    Атомарно проверить/создать/присоединиться к комнате в рамках одного захвата _LOCK.

    Возвращает строку-статус: "created" | "joined" | "locked" | "full" | "waiting".
    При "created"/"joined" комната уже создана/участник добавлен.
    При "locked"/"full"/"waiting" комната существует, но участник НЕ добавлен.

    Позволяет избежать race condition, когда два одновременных вызова
    get_room → create_room создают две комнаты с одним кодом.
    """
    with _LOCK:
        room = _ROOMS.get(room_id)
        if room is None:
            room = RoomState(room_id, sid, peer_id)
            host = Participant(sid, peer_id, name, user_id)
            host.role = ROLE_HOST
            room.participants[peer_id] = host
            room.sid_to_peer[sid] = peer_id
            _ROOMS[room_id] = room
            logger.info("[room] created room=%s host=%s", room_id, peer_id)
            return "created"
        # Комната существует
        if room.flags.get("locked"):
            return "locked"
        if len(room.participants) >= MAX_PARTICIPANTS:
            return "full"
        if room.flags.get("waiting_room"):
            room.waiting_queue.append({"sid": sid, "name": name, "peer_id": peer_id})
            return "waiting"
        p = Participant(sid, peer_id, name, user_id)
        room.participants[peer_id] = p
        room.sid_to_peer[sid] = peer_id
        room.last_active = time.time()
        logger.info("[room] join room=%s peer=%s name=%s", room_id, peer_id, name)
        return "joined"


def leave_room(room_id: str, sid: str) -> Optional[RoomState]:
    """Удалить участника из комнаты."""
    with _LOCK:
        room = _ROOMS.get(room_id)
        if room is None:
            return None
        peer_id = room.sid_to_peer.pop(sid, None)
        if peer_id:
            room.participants.pop(peer_id, None)
            room.last_active = time.time()
            # Если организатор ушёл — передать роль следующему
            if peer_id == room.host_id and room.participants:
                # Назначить первого co-host или participant как нового host
                new_host = next(iter(room.participants.values()))
                new_host.role = ROLE_HOST
                room.host_id = new_host.peer_id
                logger.info("[room] host transferred to peer=%s in room=%s",
                            new_host.peer_id, room_id)
            logger.info("[room] leave room=%s peer=%s", room_id, peer_id)
        # Дропнуть пустую комнату
        if not room.participants:
            _ROOMS.pop(room_id, None)
            logger.info("[room] deleted empty room=%s", room_id)
            return None
        return room


def change_role(room_id: str, actor_sid: str, target_peer_id: str,
                new_role: str) -> bool:
    """Изменить роль участника. Возвращает True если успешно."""
    with _LOCK:
        room = _ROOMS.get(room_id)
        if room is None:
            return False
        actor = room.get_participant_by_sid(actor_sid)
        if actor is None:
            return False
        target = room.get_participant_by_peer(target_peer_id)
        if target is None:
            return False

        if new_role == ROLE_CO_HOST:
            if not has_permission(actor.role, "assign_co_host"):
                return False
            target.role = ROLE_CO_HOST
            return True
        elif new_role == ROLE_HOST:
            if not has_permission(actor.role, "transfer_host"):
                return False
            actor.role = ROLE_PARTICIPANT  # бывший host становится participant
            target.role = ROLE_HOST
            room.host_id = target.peer_id
            return True
        elif new_role == ROLE_PARTICIPANT:
            # Снять co-host (только host может)
            if not has_permission(actor.role, "assign_co_host"):
                return False
            target.role = ROLE_PARTICIPANT
            return True
        return False


def kick_participant(room_id: str, actor_sid: str,
                     target_peer_id: str) -> Optional[str]:
    """Удалить участника из комнаты. Возвращает sid исключённого или None."""
    with _LOCK:
        room = _ROOMS.get(room_id)
        if room is None:
            return None
        actor = room.get_participant_by_sid(actor_sid)
        if actor is None:
            return None
        target = room.get_participant_by_peer(target_peer_id)
        if target is None:
            return None
        if not has_permission(actor.role, "kick"):
            return None
        target_sid = target.sid
        room.participants.pop(target_peer_id, None)
        for s, p in dict(room.sid_to_peer).items():
            if p == target_peer_id:
                room.sid_to_peer.pop(s, None)
        return target_sid


def set_flag(room_id: str, actor_sid: str, flag: str, value: bool) -> bool:
    """Установить флаг комнаты (lock, waiting_room, и т.д.)"""
    with _LOCK:
        room = _ROOMS.get(room_id)
        if room is None:
            return False
        actor = room.get_participant_by_sid(actor_sid)
        if actor is None:
            return False
        if not has_permission(actor.role, "manage_waiting"):
            return False
        if flag in room.flags:
            room.flags[flag] = value
            return True
        return False


def add_to_waiting(room_id: str, data: Dict[str, Any]) -> bool:
    """Добавить участника в очередь ожидания."""
    with _LOCK:
        room = _ROOMS.get(room_id)
        if room is None:
            return False
        room.waiting_queue.append(data)
        return True


def admit_from_waiting(room_id: str, actor_sid: str,
                       target_idx: int = -1) -> Optional[Dict[str, Any]]:
    """Принять участника из очереди ожидания."""
    with _LOCK:
        room = _ROOMS.get(room_id)
        if room is None:
            return None
        actor = room.get_participant_by_sid(actor_sid)
        if actor is None or not has_permission(actor.role, "manage_waiting"):
            return None
        if not room.waiting_queue:
            return None
        if target_idx < 0:
            return room.waiting_queue.pop(0)
        if target_idx < len(room.waiting_queue):
            return room.waiting_queue.pop(target_idx)
        return None


def _gc() -> None:
    """Очистка stale-комнат. Запускается периодически."""
    now = time.time()
    with _LOCK:
        to_drop = []
        for rid, room in _ROOMS.items():
            if now - room.last_active > ROOM_TTL_SECONDS:
                to_drop.append(rid)
        for rid in to_drop:
            _ROOMS.pop(rid, None)
            logger.info("[room] GC removed stale room=%s", rid)
