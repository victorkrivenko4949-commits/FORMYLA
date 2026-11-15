# -*- coding: utf-8 -*-
"""services/seat_premium.py — SEAT_PREMIUM_V1 (15.11.2026, владелец).

Подписка на места (routes/seat_pay.py) теперь включает Premium «Работяга»
(premium_intense, 800 ₽) для КАЖДОГО привязанного ученика/ребёнка в
пределах лимита мест — на любом тарифе мест (1, 5, 15, 50).

Как работает (ленивая синхронизация на стороне ученика):
  * раз в CHECK_INTERVAL_SEC на запросе вошедшего ученика проверяем, привязан
    ли он (status='accepted') к родителю (parent_child_links) или учителю
    (teacher_group_members → teacher_groups) с активной seat_subscriptions;
  * привязка должна помещаться в лимит мест (первые N привязок по id);
  * если да и своего Premium у ученика нет — активируем premium_intense до
    даты окончания подписки на места, payment_id = 'seat:<id владельца>',
    amount_rub = 0 (деньги уже учтены в платеже за места);
  * владелец продлил места — срок у ученика продлевается;
  * ученика отвязали / место не помещается в лимит — seat-Premium снимается;
  * собственный оплаченный (или бета) Premium ученика НЕ трогаем;
    пробный день заменяется seat-Premium.

Отдельные хуки в маршрутах привязки не нужны: любой способ привязки
(код, никнейм, ссылка) подхватывается на следующем запросе ученика.

Отключить без деплоя: SEAT_PREMIUM_ENABLED=0.
Ошибки никогда не роняют запрос; при ошибке проверки Premium не снимается.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime

from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)

SEAT_PREMIUM_PLAN = 'premium_intense'   # «Работяга», 800 ₽
PAYMENT_PREFIX = 'seat:'
CHECK_INTERVAL_SEC = 60

_last_check: dict = {}


def seat_premium_enabled() -> bool:
    return os.environ.get('SEAT_PREMIUM_ENABLED', '1').strip().lower() \
        in ('1', 'true', 'yes', 'on')


def _as_dt(v):
    """expires_at может прийти строкой (SQLite) — приводим к naive datetime."""
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.replace('Z', '+00:00'))
        except ValueError:
            return None
    if isinstance(v, datetime) and v.tzinfo is not None:
        v = v.replace(tzinfo=None)
    return v


def _eligible_owners(child_id: int, now: datetime) -> list:
    """[(owner_id, seat_expires_at)] — владельцы активных подписок на места,
    к которым ученик привязан и помещается в лимит мест. Бросает при ошибке БД."""
    out = []

    # Родители
    rows = db.session.execute(text(
        "SELECT l.id, l.parent_id, s.seats, s.expires_at"
        " FROM parent_child_links l"
        " JOIN seat_subscriptions s ON s.user_id = l.parent_id"
        " WHERE l.child_id = :c AND l.status = 'accepted'"
        " AND s.expires_at > :now"
    ), {'c': child_id, 'now': now}).fetchall()
    for link_id, owner_id, seats, exp in rows:
        rank = db.session.execute(text(
            "SELECT COUNT(*) FROM parent_child_links"
            " WHERE parent_id = :o AND status = 'accepted' AND id <= :lid"
        ), {'o': owner_id, 'lid': link_id}).scalar() or 0
        exp_dt = _as_dt(exp)
        if exp_dt is not None and int(rank) <= int(seats or 0):
            out.append((int(owner_id), exp_dt))

    # Учителя
    rows = db.session.execute(text(
        "SELECT m.id, g.teacher_id, s.seats, s.expires_at"
        " FROM teacher_group_members m"
        " JOIN teacher_groups g ON g.id = m.group_id"
        " JOIN seat_subscriptions s ON s.user_id = g.teacher_id"
        " WHERE m.user_id = :c AND m.status = 'accepted'"
        " AND s.expires_at > :now"
    ), {'c': child_id, 'now': now}).fetchall()
    for member_id, owner_id, seats, exp in rows:
        rank = db.session.execute(text(
            "SELECT COUNT(*) FROM teacher_group_members m2"
            " JOIN teacher_groups g2 ON g2.id = m2.group_id"
            " WHERE g2.teacher_id = :o AND m2.status = 'accepted'"
            " AND m2.id <= :mid"
        ), {'o': owner_id, 'mid': member_id}).scalar() or 0
        exp_dt = _as_dt(exp)
        if exp_dt is not None and int(rank) <= int(seats or 0):
            out.append((int(owner_id), exp_dt))

    return out


def sync_child_seat_premium(child_id: int) -> str:
    """Привести Premium ученика в соответствие с подписками на места.

    Возвращает: 'activated' | 'extended' | 'ok' | 'own' | 'revoked' |
    'none' | 'error'. Никогда не бросает.
    """
    now = datetime.utcnow()
    try:
        owners = _eligible_owners(child_id, now)
        rows = db.session.execute(text(
            "SELECT id, expires_at, payment_id, is_trial FROM subscriptions"
            " WHERE user_id = :u AND status = 'active'"
            " AND (expires_at IS NULL OR expires_at > :now)"
            " AND plan LIKE 'premium%'"
        ), {'u': child_id, 'now': now.isoformat()}).fetchall()
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[seat_premium] lookup failed user=%s: %r', child_id, exc)
        return 'error'

    def _is_seat(r) -> bool:
        return str(r[2] or '').startswith(PAYMENT_PREFIX)

    seat_rows = [r for r in rows if _is_seat(r)]
    # свой Premium: не seat и не пробный день
    own_rows = [r for r in rows if not _is_seat(r) and not r[3]]

    try:
        if not owners:
            if not seat_rows:
                return 'none'
            for r in seat_rows:
                db.session.execute(text(
                    "UPDATE subscriptions SET status = 'cancelled' WHERE id = :id"
                ), {'id': r[0]})
            if not own_rows:
                db.session.execute(text(
                    "UPDATE users SET current_plan = 'free', plan_expires_at = NULL"
                    " WHERE id = :u"
                ), {'u': child_id})
            db.session.commit()
            logger.info('[seat_premium] revoked for user=%s', child_id)
            return 'revoked'

        owner_id, seat_exp = max(owners, key=lambda o: o[1])
        payment_id = f'{PAYMENT_PREFIX}{owner_id}'

        if seat_rows:
            r = max(seat_rows, key=lambda x: x[0])
            cur_exp = _as_dt(r[1])
            same_owner = (r[2] == payment_id)
            if same_owner and cur_exp is not None \
                    and (seat_exp - cur_exp).total_seconds() < 60:
                return 'ok'
            db.session.execute(text(
                "UPDATE subscriptions SET expires_at = :e, payment_id = :p"
                " WHERE id = :id"
            ), {'e': seat_exp.isoformat(), 'p': payment_id, 'id': r[0]})
            if not own_rows:
                db.session.execute(text(
                    "UPDATE users SET current_plan = 'premium', plan_expires_at = :e"
                    " WHERE id = :u"
                ), {'e': seat_exp.isoformat(), 'u': child_id})
            db.session.commit()
            logger.info('[seat_premium] extended user=%s until %s (owner=%s)',
                        child_id, seat_exp, owner_id)
            return 'extended'

        if own_rows:
            return 'own'  # свой оплаченный Premium не трогаем

        from services.subscription import get_subscription_service
        get_subscription_service().activate_premium(
            user_id=child_id, plan=SEAT_PREMIUM_PLAN,
            payment_id=payment_id, is_beta=False, expires_at=seat_exp)
        # Деньги учтены в платеже за места — в подписке ученика сумма 0.
        db.session.execute(text(
            "UPDATE subscriptions SET amount_rub = 0"
            " WHERE user_id = :u AND payment_id = :p AND status = 'active'"
        ), {'u': child_id, 'p': payment_id})
        db.session.commit()
        logger.info('[seat_premium] activated %s for user=%s until %s (owner=%s)',
                    SEAT_PREMIUM_PLAN, child_id, seat_exp, owner_id)
        return 'activated'
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[seat_premium] sync failed user=%s: %r', child_id, exc)
        return 'error'


def install_seat_premium(app) -> None:
    """before_request-хук: ленивая синхронизация seat-Premium для учеников.

    Ставится ПЕРВЫМ в цепочке before_request, чтобы paywall на этом же
    запросе уже видел выданный Premium.
    """
    if app.extensions.get('seat_premium_installed'):
        return
    app.extensions['seat_premium_installed'] = True

    def _seat_premium_sync():
        try:
            if not seat_premium_enabled():
                return None
            from flask import request
            path = request.path or ''
            if path.startswith('/static') or path == '/healthz':
                return None
            from flask_login import current_user
            if not getattr(current_user, 'is_authenticated', False):
                return None
            role = getattr(current_user, 'role', 'student') or 'student'
            if role in ('parent', 'teacher'):
                return None
            uid = int(current_user.id)
            t = time.monotonic()
            last = _last_check.get(uid)
            if last is not None and t - last < CHECK_INTERVAL_SEC:
                return None
            if len(_last_check) > 20000:
                _last_check.clear()
            _last_check[uid] = t
            sync_child_seat_premium(uid)
        except Exception as exc:  # noqa: BLE001 — хук не должен ронять запрос
            logger.warning('[seat_premium] hook failed: %r', exc)
            try:
                db.session.rollback()
            except Exception:  # noqa: BLE001
                pass
        return None

    app.before_request_funcs.setdefault(None, []).insert(0, _seat_premium_sync)
    logger.info('seat_premium installed: enabled=%s plan=%s',
                seat_premium_enabled(), SEAT_PREMIUM_PLAN)
