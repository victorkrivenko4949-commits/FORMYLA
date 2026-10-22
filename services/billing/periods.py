# -*- coding: utf-8 -*-
"""Расчёт периода доступа для заказа (BILLING_V1).

Правила:
  * access_starts_at = max(сейчас, конец действующего ОПЛАЧЕННОГО доступа);
  * Основатель, купивший год до 01.02.2027 00:00 МСК: период
    01.02.2027 00:00 МСК → 01.02.2028 00:00 МСК;
  * пересекающийся оплаченный период не сокращаем; если правило неясно —
    PeriodRuleUnclear с понятным объяснением (заказ блокируется).
Бизнес-время — Europe/Moscow через zoneinfo; хранение — UTC.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta

from .catalog import Product, user_is_founder_priced

logger = logging.getLogger(__name__)
MSK = ZoneInfo('Europe/Moscow')
UTC = timezone.utc


class PeriodRuleUnclear(Exception):
    """Правило начала периода неоднозначно — заказ не создаём."""


def env_dt(name: str, default_iso: str) -> datetime:
    raw = (os.environ.get(name) or default_iso).strip().replace('Z', '+00:00')
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def founder_grant_until() -> datetime:
    # = 01.02.2027 00:00 МСК
    return env_dt('FOUNDER_GRANT_UNTIL', '2027-01-31T21:00:00Z')


def to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


def to_aware_utc(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def add_year_msk(start: datetime) -> datetime:
    """Календарный год по московскому времени."""
    local = start.astimezone(MSK)
    return (local + relativedelta(years=1)).astimezone(UTC)


def current_paid_access_end(user_id: int) -> Optional[datetime]:
    """Конец действующего ОПЛАЧЕННОГО доступа (aware UTC) или None.

    Здесь намеренно НЕ используется services.access.resolve_access:
    resolve_access отвечает на вопрос «есть ли доступ ПРЯМО СЕЙЧАС» и
    игнорирует будущие строки (год Основателя с 01.02.2027, продление
    поверх действующего периода). Для расчёта начала нового периода нужны
    все активные оплаченные строки, включая будущие — берём MAX(expires_at).
    CAST(... AS INTEGER) работает и для INTEGER (SQLite), и для BOOLEAN (PostgreSQL).
    Любая ошибка → None (новый период начнётся «сейчас»); это не выдаёт доступ,
    поэтому fail-open здесь безопасен.
    """
    try:
        from sqlalchemy import text
        from models import db
        from models import db as _db
        _pg = _db.engine.dialect.name == 'postgresql'
        _max = 'MAX(expires_at)' if _pg else 'MAX(datetime(expires_at))'
        row = db.session.execute(text(f"""
            SELECT {_max} AS e FROM subscriptions
            WHERE user_id = :u AND status = 'active' AND plan LIKE 'premium%'
              AND payment_id IS NOT NULL
              AND COALESCE(CAST(is_trial AS INTEGER), 0) = 0
              AND COALESCE(CAST(is_beta_access AS INTEGER), 0) = 0
        """), {'u': user_id}).first()
        if row and row[0]:
            return to_aware_utc(row[0])
    except Exception as exc:
        logger.warning('billing.periods: paid end lookup failed user=%s: %s', user_id, exc)
    return None


def compute_period(product: Product, user, now: Optional[datetime] = None
                   ) -> Tuple[Optional[datetime], Optional[datetime]]:
    """(starts_at, ends_at) aware UTC; (None, None) для разовых покупок."""
    if product.kind != 'access':
        return None, None
    now = (now or datetime.now(UTC)).astimezone(UTC)
    paid_end = current_paid_access_end(user.id)
    if paid_end is not None and paid_end <= now:
        paid_end = None

    if product.duration == '1y' and user_is_founder_priced(user):
        cutoff = founder_grant_until()
        if now < cutoff:
            starts = cutoff
            if paid_end is not None and paid_end > starts:
                raise PeriodRuleUnclear(
                    'У вас уже есть оплаченный доступ после 1 февраля 2027. '
                    'Чтобы не потерять ни дня, напишите в поддержку — мы оформим '
                    'продление вручную.')
            return starts, add_year_msk(starts)

    starts = max(now, paid_end) if paid_end else now
    if product.duration == '30d':
        return starts, starts + timedelta(days=30)
    if product.duration == '1y':
        return starts, add_year_msk(starts)
    raise PeriodRuleUnclear(f'Неизвестная длительность тарифа {product.code}.')
