# -*- coding: utf-8 -*-
"""TG_TRIAL_WEEK (05.11.2026) — неделя Premium за подписку на Telegram-канал.

Поток для пользователя (одна кнопка):
  1. «Открыть канал» → подписывается на @FormylaMaths.
  2. «Проверить подписку и получить неделю»:
     • Telegram уже привязан (вход через ТГ / привязка в профиле) — сразу проверка;
     • не привязан — Telegram Login Widget, подпись проверяем тем же HMAC,
       что и при входе, привязываем Telegram к аккаунту и проверяем.
  3. Сервер спрашивает Bot API getChatMember(канал, telegram_id).
     Подписан → выдаём ровно 7 дней Premium «Работяга».

Правила:
  • одна неделя на аккаунт и одна на Telegram-аккаунт (таблица tg_trial_grants);
  • если идёт пробный день — неделя его заменяет (срок = сейчас + 7 дней);
  • если уже есть оплаченный/пилотный Premium — неделя не нужна;
  • родитель/учитель — как с пробным днём: только в аккаунте ребёнка;
  • после выдачи отписка доступ не отзывает (честная акция, без «ловушек»).

Важно для работы: бот TELEGRAM_BOT_TOKEN должен быть АДМИНИСТРАТОРОМ канала,
иначе Telegram не отдаёт статус подписчика (ответ «member list is inaccessible»).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import requests
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from models import db

log = logging.getLogger(__name__)

TRIAL_WEEK_DAYS = 7          # ровно неделя — не настраивается через env намеренно
TRIAL_WEEK_PLAN = 'premium_intense'
_MEMBER_STATUSES = {'creator', 'administrator', 'member'}


def channel_username() -> str:
    """@username канала без «@». По умолчанию — официальный канал FORMYLA."""
    raw = (os.environ.get('TG_TRIAL_CHANNEL') or 'FormylaMaths').strip()
    return raw.lstrip('@')


def channel_url() -> str:
    return f'https://t.me/{channel_username()}'


def _bot_token() -> str:
    return (os.environ.get('TELEGRAM_BOT_TOKEN') or '').strip()


class TgTrialError(Exception):
    """Ошибка с понятным пользователю текстом и кодом для фронтенда."""

    def __init__(self, code: str, message: str, http: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http = http


# ───────────────────────── Bot API ─────────────────────────

def check_membership(telegram_id: str) -> bool:
    """True, если telegram_id подписан на канал. Ошибки конфигурации → TgTrialError."""
    token = _bot_token()
    if not token:
        log.error('[tg_trial] TELEGRAM_BOT_TOKEN не задан')
        raise TgTrialError('config', 'Проверка подписки временно недоступна. Попробуй чуть позже.', 503)
    try:
        resp = requests.get(
            f'https://api.telegram.org/bot{token}/getChatMember',
            params={'chat_id': '@' + channel_username(), 'user_id': telegram_id},
            timeout=8,
        )
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — сеть/JSON
        log.warning('[tg_trial] getChatMember network error: %r', exc)
        raise TgTrialError('network', 'Telegram не ответил. Нажми «Проверить» ещё раз через пару секунд.', 503)

    if not data.get('ok'):
        desc = str(data.get('description') or '')
        # «user not found» — пользователь ни разу не заходил в канал → не подписан.
        if 'user not found' in desc.lower() or 'participant_id_invalid' in desc.lower():
            return False
        log.error('[tg_trial] getChatMember failed: %s (бот должен быть админом канала)', desc)
        raise TgTrialError('config', 'Проверка подписки временно недоступна. Попробуй чуть позже.', 503)

    member = data.get('result') or {}
    status = member.get('status')
    if status in _MEMBER_STATUSES:
        return True
    # restricted — участник с ограничениями, подписка есть, если is_member
    return status == 'restricted' and bool(member.get('is_member'))


# ───────────────────────── Состояние ─────────────────────────

def _now() -> datetime:
    return datetime.utcnow()


def _role_blocked(user) -> bool:
    return (getattr(user, 'role', 'student') or 'student') in ('parent', 'teacher')


def _has_real_premium(user) -> bool:
    """Оплаченный / бета / пилотный Premium (пробные — не считаются)."""
    try:
        from services.pilot import is_pilot_user
        if is_pilot_user(user):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        row = db.session.execute(text(
            "SELECT 1 FROM subscriptions WHERE user_id = :u AND status = 'active' "
            "AND plan LIKE 'premium%' AND COALESCE(CAST(is_trial AS INTEGER),0) = 0 "
            "AND (expires_at IS NULL OR expires_at > :now) LIMIT 1"
        ), {'u': user.id, 'now': _now().isoformat(sep=' ')}).first()
        return row is not None
    except Exception:  # noqa: BLE001
        return False


def _grant_for(user_id: int):
    from models_tg_trial import TgTrialGrant
    return TgTrialGrant.query.filter_by(user_id=user_id).first()


def get_state(user) -> dict:
    """Что показать пользователю. state:
       hidden     — гость/аноним/родитель/учитель: ничего не показываем;
       premium    — уже есть настоящий Premium;
       active     — неделя идёт (expires_at);
       used       — неделя уже была;
       available  — можно получить (tg_linked — привязан ли Telegram).
    """
    base = {'channel': channel_username(), 'channel_url': channel_url(), 'days': TRIAL_WEEK_DAYS}
    if not getattr(user, 'is_authenticated', False) or getattr(user, 'is_guest', False):
        return {**base, 'state': 'hidden'}
    if _role_blocked(user) or not _bot_token():
        return {**base, 'state': 'hidden'}
    try:
        grant = _grant_for(user.id)
    except Exception:  # noqa: BLE001 — таблицы ещё нет и т.п.
        return {**base, 'state': 'hidden'}
    if grant is not None:
        if grant.expires_at > _now():
            return {**base, 'state': 'active', 'expires_at': grant.expires_at.isoformat(sep=' ')}
        return {**base, 'state': 'used'}
    if _has_real_premium(user):
        return {**base, 'state': 'premium'}
    try:
        trial_day = bool(user.is_trial_active())
    except Exception:  # noqa: BLE001
        trial_day = False
    return {**base, 'state': 'available',
            'tg_linked': bool(getattr(user, 'telegram_id', None)),
            'tg_username': getattr(user, 'telegram_username', None) or '',
            'trial_day_active': trial_day}


# ───────────────────────── Выдача ─────────────────────────

def link_telegram(user, payload: dict) -> None:
    """Привязать Telegram к аккаунту по подписанному payload Login Widget."""
    from models import User
    from routes.telegram_auth import verify_telegram_payload

    clean = {k: str(v) for k, v in (payload or {}).items() if v is not None}
    if not verify_telegram_payload(clean):
        raise TgTrialError('tg_auth', 'Не удалось подтвердить Telegram. Попробуй войти ещё раз.', 400)
    tg_id = clean.get('id', '').strip()
    if not tg_id:
        raise TgTrialError('tg_auth', 'Telegram не передал id. Попробуй ещё раз.', 400)
    existing = User.query.filter_by(telegram_id=tg_id).first()
    if existing is not None and existing.id != user.id:
        raise TgTrialError('tg_taken', 'Этот Telegram уже привязан к другому аккаунту FORMYLA.', 409)
    user.telegram_id = tg_id
    user.telegram_username = (clean.get('username') or '').strip() or None
    db.session.commit()


def claim_week(user, tg_auth: Optional[dict] = None) -> dict:
    """Проверить подписку и выдать неделю. Возвращает {'expires_at': iso}."""
    from models_tg_trial import TgTrialGrant

    state = get_state(user)
    st = state['state']
    if st == 'hidden':
        if _role_blocked(user):
            raise TgTrialError('role', 'Неделя Premium оформляется в аккаунте ребёнка.', 403)
        raise TgTrialError('auth', 'Войди в аккаунт, чтобы получить неделю.', 403)
    if st == 'active':
        raise TgTrialError('already_active', 'Неделя Premium уже активна.', 409)
    if st == 'used':
        raise TgTrialError('used', 'Неделя за подписку уже была получена на этом аккаунте.', 409)
    if st == 'premium':
        raise TgTrialError('premium', 'У тебя уже есть Premium — неделя не нужна.', 409)

    if tg_auth:
        link_telegram(user, tg_auth)
    tg_id = str(getattr(user, 'telegram_id', '') or '').strip()
    if not tg_id:
        raise TgTrialError('need_tg', 'Подтверди свой Telegram, чтобы мы проверили подписку.', 400)

    if TgTrialGrant.query.filter_by(telegram_id=tg_id).first() is not None:
        raise TgTrialError('tg_used', 'С этого Telegram неделя уже была получена на другом аккаунте.', 409)

    if not check_membership(tg_id):
        raise TgTrialError('not_member',
                           f'Пока не видим подписку на @{channel_username()}. '
                           'Подпишись на канал и нажми «Проверить» ещё раз.', 400)

    now = _now()
    expires = now + timedelta(days=TRIAL_WEEK_DAYS)
    try:
        db.session.add(TgTrialGrant(user_id=user.id, telegram_id=tg_id,
                                    channel=channel_username(), granted_at=now, expires_at=expires))
        db.session.flush()   # уникальность: двойной клик / гонка → IntegrityError
    except IntegrityError:
        db.session.rollback()
        raise TgTrialError('used', 'Неделя за подписку уже получена.', 409)

    from services.subscription import get_subscription_service
    # activate_premium сам гасит текущий пробный день (superseded) и коммитит.
    get_subscription_service().activate_premium(
        user_id=user.id, plan=TRIAL_WEEK_PLAN, is_beta=True, is_trial=True,
        starts_at=now, expires_at=expires,
    )
    db.session.commit()
    log.info('[tg_trial] user=%s tg=%s week granted until %s', user.id, tg_id, expires)
    return {'expires_at': expires.isoformat(sep=' ')}
