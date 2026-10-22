# -*- coding: utf-8 -*-
"""services/pilot.py — пилот Premium-версии на двух аккаунтах.

Пилот: новые тарифы (premium_intense / premium_calm) и новый премиум-контент
видны только пилотным аккаунтам. Для всех остальных пользователей сайт работает
как раньше — ничего не меняется.

Пилотные аккаунты (по нику в БД):
  * victor  (id=1)  — владелец
  * Lavrik  (id=5)

Включение/выключение пилота целиком — флагом PILOT_ENABLED ниже.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger('formyla.pilot')

# ── Конфигурация пилота ─────────────────────────────────────────────────────

PILOT_ENABLED = True

# id пилотных аккаунтов: victor=1, Lavrik=5 (проверено в prod 22.10.2026)
PILOT_USER_IDS = (1, 5)

# Пилотные тарифы (см. services/subscription.py → PLAN_LIMITS)
PILOT_PLANS = ('premium_intense', 'premium_calm')

# Тариф, который активируется пилотным аккаунтам по умолчанию (бета, без оплаты)
PILOT_DEFAULT_PLAN = 'premium_intense'


# ── Хелперы ─────────────────────────────────────────────────────────────────

def is_pilot_user(user) -> bool:
    """True, если user (объект User или id) — пилотный аккаунт и пилот включён.

    Безопасен для анонимных пользователей (None → False).
    """
    if not PILOT_ENABLED:
        return False
    user_id: Optional[int] = None
    try:
        if user is None:
            return False
        # Объект User
        user_id = getattr(user, 'id', None)
        if user_id is None and isinstance(user, int):
            user_id = user
    except Exception:
        return False
    if not user_id:
        return False
    return int(user_id) in PILOT_USER_IDS


def is_pilot_id(user_id) -> bool:
    """True, если user_id — пилотный id и пилот включён."""
    if not PILOT_ENABLED:
        return False
    try:
        return int(user_id) in PILOT_USER_IDS
    except (TypeError, ValueError):
        return False


# ── Активация бета-подписки для пилотных аккаунтов ─────────────────────────

def ensure_pilot_subscriptions() -> bool:
    """Идемпотентно выдаёт пилотным аккаунтам бета-Premium.

    Вызывается на старте приложения (после auto_migrate). Для каждого
    пилотного id: если нет активной подписки — активирует PILOT_DEFAULT_PLAN
    с is_beta=True (без оплаты). Существующие подписки не трогает.

    Атомарность: успешный commit → True; любая ошибка → rollback и False.
    Никогда не бросает исключение наружу (пилот не должен ронять старт).
    """
    if not PILOT_ENABLED:
        return False
    try:
        from models import db as _models_db
        from services.subscription import get_subscription_service
        svc = get_subscription_service()
        dirty = False
        for user_id in PILOT_USER_IDS:
            try:
                plan_info = svc.get_user_plan(user_id)
                if plan_info.get('is_premium'):
                    continue  # уже есть активная подписка — не трогаем
                svc.activate_premium(
                    user_id=user_id,
                    plan=PILOT_DEFAULT_PLAN,
                    is_beta=True,
                )
                dirty = True
                logger.info('[PILOT] user %s: activating beta plan %s',
                            user_id, PILOT_DEFAULT_PLAN)
            except Exception as e:
                logger.warning('[PILOT] user %s: activation failed: %s', user_id, e)
                try:
                    _models_db.session.rollback()
                except Exception:
                    pass
        # Активация идёт вне HTTP-запроса (на старте приложения), поэтому
        # фиксируем транзакцию явно — SubscriptionService в SQLAlchemy-режиме
        # сознательно не коммитит сам (в запросах это делает Flask).
        # Успешный commit — единственный источник успешного результата.
        if dirty:
            try:
                _models_db.session.commit()
                return True
            except Exception as e:
                logger.warning('[PILOT] commit failed: %s', e)
                try:
                    _models_db.session.rollback()
                except Exception:
                    pass
                return False
        return False
    except Exception as e:
        logger.warning('[PILOT] ensure_pilot_subscriptions failed: %s', e)
        return False
