# -*- coding: utf-8 -*-
'''
routes/site_notices.py — SITE_NOTICE_V1 (11.10.2026).

Одноразовые уведомления на сайте («Вы уже решили, какие олимпиады писать?»).
Работает по той же схеме, что и опрос «Как тебе сайт?»: фронтенд опрашивает
/api/site-notice/pending, сервер хранит отметку «показано» на пользователя
в таблице site_notice_seen (создаётся сама при первом обращении).

АДРЕСНЫЕ уведомления (13.10.2026): ключ retake_intake показывается только
конкретным пользователям из RETAKE_INTAKE_TARGETS (по никнейму или e-mail),
которым нужно перепройти анкету. Остальные его не видят.

Endpoints:
  GET  /api/site-notice/pending?key=olympiad_choice  — {pending: bool, data: {...}}
  GET  /api/site-notice/pending?key=retake_intake    — {pending: bool, data: {...}} (только адресатам)
  POST /api/site-notice/seen   {key}                 — {ok: true}
'''
from __future__ import annotations

import logging
import os
from datetime import date, datetime

from flask import Blueprint, jsonify, request
from flask_login import current_user
from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)

site_notices_bp = Blueprint('site_notices', __name__)

# Ключи уведомлений, которые разрешено показывать. Новое уведомление —
# добавь ключ сюда и ветку в _notice_payload().
NOTICE_KEYS = {'olympiad_choice', 'retake_intake'}

# Адресаты уведомления «Пройди анкету заново». Сравниваем без учёта регистра
# с User.nickname и с частью e-mail до «@». Дополнительные адресаты можно
# задать через переменную окружения RETAKE_INTAKE_USERS="nick1,nick2,mail@x.ru".
RETAKE_INTAKE_TARGETS = {'gordetskaya2008'}

_table_ready = False

_DDL_PG = '''
CREATE TABLE IF NOT EXISTS site_notice_seen (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    notice_key VARCHAR(64) NOT NULL,
    seen_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_site_notice_seen UNIQUE (user_id, notice_key)
)
'''

_DDL_SQLITE = '''
CREATE TABLE IF NOT EXISTS site_notice_seen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    notice_key VARCHAR(64) NOT NULL,
    seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, notice_key)
)
'''


def _ensure_table() -> None:
    global _table_ready
    if _table_ready:
        return
    try:
        dialect = db.engine.dialect.name
        db.session.execute(text(_DDL_PG if dialect == 'postgresql' else _DDL_SQLITE))
        db.session.commit()
        _table_ready = True
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[site_notices] ensure_table failed: %r', e)


def _seen(user_id: int, key: str) -> bool:
    _ensure_table()
    try:
        row = db.session.execute(
            text('SELECT 1 FROM site_notice_seen WHERE user_id = :u AND notice_key = :k LIMIT 1'),
            {'u': user_id, 'k': key},
        ).first()
        return row is not None
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[site_notices] seen check failed: %r', e)
        # При сбое БД считаем «уже показано», чтобы не спамить пользователя.
        return True


def _mark_seen(user_id: int, key: str) -> None:
    _ensure_table()
    try:
        if not _seen(user_id, key):
            db.session.execute(
                text('INSERT INTO site_notice_seen (user_id, notice_key, seen_at) VALUES (:u, :k, :t)'),
                {'u': user_id, 'k': key, 't': datetime.utcnow()},
            )
            db.session.commit()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[site_notices] mark_seen failed: %r', e)


# ── Адресное уведомление retake_intake ──────────────────────────────────────────────

def _retake_targets() -> set:
    '''Список адресатов: константа + переменная окружения RETAKE_INTAKE_USERS.'''
    targets = {t.lower() for t in RETAKE_INTAKE_TARGETS}
    extra = os.environ.get('RETAKE_INTAKE_USERS', '') or ''
    for part in extra.split(','):
        part = part.strip().lower()
        if part:
            targets.add(part)
    return targets


def _is_retake_target(user) -> bool:
    '''Пользователь — адресат уведомления «Пройди анкету заново»?'''
    targets = _retake_targets()
    nick = (getattr(user, 'nickname', None) or '').strip().lower()
    email = (getattr(user, 'email', None) or '').strip().lower()
    local = email.split('@', 1)[0] if email else ''
    return bool(
        (nick and nick in targets)
        or (email and email in targets)
        or (local and local in targets)
    )


def _already_retook_intake(user_id: int) -> bool:
    '''Анкета уже была сброшена через /intake/restart (prep_state.intake_retakes > 0)?'''
    try:
        from models_curator import CuratorState
        from services.intake_service import _prep_state_dict
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if not cs:
            return False
        ps = _prep_state_dict(cs)
        return int(ps.get('intake_retakes') or 0) > 0
    except Exception as e:  # noqa: BLE001
        logger.warning('[site_notices] retake check failed: %r', e)
        return False


def _notice_payload(key: str) -> dict:
    '''Данные для отрисовки уведомления на фронте.'''
    if key == 'retake_intake':
        name = ''
        try:
            name = (getattr(current_user, 'nickname', None) or '').strip()
        except Exception:  # noqa: BLE001
            name = ''
        return {
            'restart_url': '/intake/restart',
            'nickname': name,
        }
    if key == 'olympiad_choice':
        try:
            from olympiad_calendar_data import build_calendar
            cards, summary, today = build_calendar([], date.today())

            def pack(lst):
                return [
                    {
                        'short': c['short'],
                        'key': c['key'],
                        'reg_text': c['registration']['text'],
                        'days_left': c['reg_days_left'],
                        'reg_end': c['registration']['end'].strftime('%d.%m.%Y') if c['registration']['end'] else None,
                    }
                    for c in lst
                ]

            return {
                'open': pack(summary['open']),
                'upcoming': pack(summary['upcoming']),
                'closed': pack(summary['closed']),
                'today': today.strftime('%d.%m.%Y'),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning('[site_notices] payload failed: %r', e)
            return {}
    return {}


@site_notices_bp.route('/api/site-notice/pending')
def pending():
    key = (request.args.get('key') or '').strip()
    if key not in NOTICE_KEYS:
        return jsonify({'pending': False})

    # Адресное уведомление: только авторизованным адресатам, гостям — никогда.
    if key == 'retake_intake':
        if not current_user.is_authenticated or getattr(current_user, 'is_guest', False):
            return jsonify({'pending': False})
        if not _is_retake_target(current_user):
            return jsonify({'pending': False})
        if _seen(current_user.id, key) or _already_retook_intake(current_user.id):
            return jsonify({'pending': False})
        return jsonify({'pending': True, 'data': _notice_payload(key)})

    if not current_user.is_authenticated or getattr(current_user, 'is_guest', False):
        # Гостям сервер ничего не хранит — фронт использует localStorage.
        return jsonify({'pending': True, 'guest': True, 'data': _notice_payload(key)})
    if _seen(current_user.id, key):
        return jsonify({'pending': False})
    return jsonify({'pending': True, 'data': _notice_payload(key)})


@site_notices_bp.route('/api/site-notice/seen', methods=['POST'])
def seen():
    payload = request.get_json(silent=True) or {}
    key = (payload.get('key') or '').strip()
    if key not in NOTICE_KEYS:
        return jsonify({'ok': False, 'error': 'unknown key'}), 400
    if current_user.is_authenticated and not getattr(current_user, 'is_guest', False):
        _mark_seen(current_user.id, key)
    return jsonify({'ok': True})
