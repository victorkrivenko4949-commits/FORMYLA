# -*- coding: utf-8 -*-
"""
Blueprint: трекинг событий.

Endpoints:
  POST /api/track        — лог события из JS (без авторизации)
  before_app_request     — сохраняет UTM-метки в cookie на 30 дней
                            и обеспечивает session_id для анонимов.

Любая внутренняя точка кода может вызвать `log_event(event_name, meta=...)`
чтобы атомарно записать событие с уже разобранным контекстом (UTM, session_id, path).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, current_app, g, jsonify, request
from flask_login import current_user

from models import db, Event

logger = logging.getLogger(__name__)

track_bp = Blueprint('track', __name__)

UTM_KEYS = ('utm_source', 'utm_medium', 'utm_campaign', 'utm_content')
UTM_COOKIE_MAX_AGE = 60 * 60 * 24 * 30          # 30 дней
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 365     # 1 год
SESSION_COOKIE_NAME = 'fm_sid'


# ─────────────────────────────────────────────────────────────────────────────
# Public helper, can be called from any route to log an event.
# ─────────────────────────────────────────────────────────────────────────────
def log_event(event: str, meta: dict | None = None, user_id: int | None = None) -> None:
    """Сохранить событие в БД (best-effort, не падает наружу)."""
    try:
        utm = getattr(g, 'utm', {}) or {}
        session_id = getattr(g, 'analytics_session_id', None)

        uid = user_id
        if uid is None:
            if current_user.is_authenticated:
                uid = current_user.id

        ev = Event(
            user_id=uid,
            session_id=session_id,
            event=(event or '')[:64] or 'unknown',
            utm_source=(utm.get('utm_source') or None) and utm['utm_source'][:64],
            utm_medium=(utm.get('utm_medium') or None) and utm['utm_medium'][:64],
            utm_campaign=(utm.get('utm_campaign') or None) and utm['utm_campaign'][:64],
            utm_content=(utm.get('utm_content') or None) and utm['utm_content'][:64],
            path=(request.path or '')[:256] if request else None,
            referer=(request.referrer or '')[:512] if request else None,
            user_agent=(request.headers.get('User-Agent', '') if request else '')[:512],
            ip=(request.headers.get('X-Forwarded-For', request.remote_addr or '') if request else '')[:64],
            meta=meta or {},
            created_at=datetime.utcnow(),
        )
        db.session.add(ev)
        db.session.commit()
    except Exception as exc:  # pragma: no cover - аналитика не должна падать
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.warning('[track] log_event(%s) failed: %s', event, exc)


# ─────────────────────────────────────────────────────────────────────────────
# UTM + session_id middleware (registered via before_app_request).
# ─────────────────────────────────────────────────────────────────────────────
@track_bp.before_app_request
def _capture_utm_and_session():
    """Считать UTM из query/cookie и подготовить session_id."""
    # 1. UTM: приоритет — query-string, fallback — cookie.
    utm = {}
    for k in UTM_KEYS:
        v = request.args.get(k)
        if not v:
            v = request.cookies.get(k)
        if v:
            utm[k] = v[:64]
    g.utm = utm
    # пометим, какие UTM пришли в этом запросе (для записи в cookie на after_request)
    g._utm_to_set = {k: request.args.get(k) for k in UTM_KEYS if request.args.get(k)}

    # 2. session_id
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if not sid:
        sid = uuid.uuid4().hex
        g._set_session_cookie = sid
    g.analytics_session_id = sid


@track_bp.after_app_request
def _write_cookies(resp):
    """Записать UTM/session_id в cookie, если нужно."""
    try:
        # session cookie
        new_sid = getattr(g, '_set_session_cookie', None)
        if new_sid:
            resp.set_cookie(
                SESSION_COOKIE_NAME,
                new_sid,
                max_age=SESSION_COOKIE_MAX_AGE,
                httponly=True,
                samesite='Lax',
                secure=request.is_secure,
            )
        # UTM cookies
        to_set = getattr(g, '_utm_to_set', None) or {}
        for k, v in to_set.items():
            if not v:
                continue
            resp.set_cookie(
                k,
                v[:64],
                max_age=UTM_COOKIE_MAX_AGE,
                httponly=False,
                samesite='Lax',
                secure=request.is_secure,
            )
    except Exception as exc:  # pragma: no cover
        logger.warning('[track] cookie write failed: %s', exc)
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Public endpoint
# ─────────────────────────────────────────────────────────────────────────────
@track_bp.route('/api/track', methods=['POST'])
def api_track():
    """Принять событие из JS."""
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}

    event_name = (payload.get('event') or '').strip()[:64]
    if not event_name:
        return jsonify({'ok': False, 'error': 'event required'}), 400

    meta = payload.get('meta') or {}
    if not isinstance(meta, dict):
        meta = {'raw': str(meta)[:500]}

    # path может прийти явно от JS (фактический URL страницы)
    path_override = (payload.get('path') or '')[:256]
    if path_override:
        meta.setdefault('client_path', path_override)

    log_event(event_name, meta=meta)
    return jsonify({'ok': True})
