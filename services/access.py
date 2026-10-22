# -*- coding: utf-8 -*-
"""FOUNDERS_V1 — services/access.py: единый порядок доступа.

resolve_access(user) → (source, expires_at):
    source: 'paid' | 'founder' | 'trial' | 'free'

Правила:
  * приоритет строгий: paid → founder → trial → free;
  * более короткий источник не сокращает более длинный (union периодов внутри
    источника, между источниками — приоритет, а не сумма);
  * платный доступ: активные subscriptions (plan LIKE 'premium%', payment_id
    IS NOT NULL, is_beta_access = 0, started_at <= now < expires_at) —
    берём MAX(expires_at). Будущие строки (год Основателя с 01.02.2027)
    начинают действовать только со своего started_at;
  * Основатель: founder_grants, starts_at <= now < expires_at;
  * триал: users.trial_until > now (User.is_trial_active() НЕ используется —
    он всегда True и до этой задачи пропускал всех через paywall);
  * ошибки → ('free', None) + лог: сайт продолжает работать, платный доступ
    при сомнении не выдаётся (fail-closed).

Бизнес-время — Europe/Moscow через zoneinfo; моменты хранятся в naive UTC
(как и весь проект: default=datetime.utcnow, сервер Render в UTC).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)

MSK = ZoneInfo('Europe/Moscow')
UTC = timezone.utc

FOUNDER_CAMPAIGN_ID = 'founders_2026_v1'
DEFAULT_FOUNDER_CUTOFF = '2026-11-02T21:00:00Z'   # = 03.11.2026 00:00 МСК
DEFAULT_FOUNDER_GRANT_UNTIL = '2027-01-31T21:00:00Z'  # = 01.02.2027 00:00 МСК

AccessSource = str  # 'paid' | 'founder' | 'trial' | 'free'


def _env_dt(name: str, default_iso: str) -> datetime:
    """env-переменная с ISO-датой → aware UTC. Битое значение → дефолт."""
    raw = (os.environ.get(name) or default_iso).strip().replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        logger.error('access: bad %s=%r, using default', name, raw)
        dt = datetime.fromisoformat(default_iso.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def founder_cutoff() -> datetime:
    """Граница Основателей: created_at < cutoff. 03.11.2026 00:00 МСК."""
    return _env_dt('FOUNDER_CUTOFF_AT', DEFAULT_FOUNDER_CUTOFF)


def founder_grant_until() -> datetime:
    """Конец бесплатного доступа Основателя. 01.02.2027 00:00 МСК (не включается)."""
    return _env_dt('FOUNDER_GRANT_UNTIL', DEFAULT_FOUNDER_GRANT_UNTIL)


def founder_grant_start() -> datetime:
    """Начало окна бесплатного доступа = граница кампании. 03.11.2026 00:00 МСК."""
    return founder_cutoff()


def _to_aware(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.replace('Z', '+00:00')
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


# ─────────────────────────── источники доступа ───────────────────────────

def _paid_expires_at(user_id: int, now: datetime) -> Optional[datetime]:
    """MAX(expires_at) по действующим оплаченным premium-подпискам.

    CAST(is_beta_access AS INTEGER) работает и для INTEGER (SQLite), и для
    BOOLEAN (PostgreSQL). is_trial-подписки не считаются оплатой.

    Исключение — тарифы пилота premium_intense/premium_calm: они выдаются
    без оплаты (is_beta), но дают ПОЛНЫЙ платный доступ — лимиты Free (3
    задачи в день и т.п.) на пилотные аккаунты не действуют. Эти тарифы
    доступны только пилотным аккаунтам (остальным /api/subscribe → 403).
    """
    now_n = _naive_utc(now)
    # started_at/expires_at могут быть записаны с 'T' или пробелом между датой
    # и временем (isoformat по умолчанию даёт 'T'). В SQLite сравниваем через
    # datetime(...) — функция понимает оба формата; в PostgreSQL колонка
    # TIMESTAMP и сравнивается как datetime.
    pg = db.engine.dialect.name == 'postgresql'
    cond = ("(started_at IS NULL OR started_at <= :now) AND expires_at > :now"
            if pg else
            "(started_at IS NULL OR datetime(started_at) <= datetime(:now)) "
            "AND datetime(expires_at) > datetime(:now)")
    try:
        max_expr = ('MAX(expires_at)' if pg else 'MAX(datetime(expires_at))')
        row = db.session.execute(text(f"""
            SELECT {max_expr} AS e
            FROM subscriptions
            WHERE user_id = :u
              AND status = 'active'
              AND plan LIKE 'premium%'
              AND (
                (payment_id IS NOT NULL
                 AND COALESCE(CAST(is_beta_access AS INTEGER), 0) = 0)
                OR plan IN ('premium_intense', 'premium_calm')
              )
              AND COALESCE(CAST(is_trial AS INTEGER), 0) = 0
              AND {cond}
        """), {'u': user_id, 'now': now_n.isoformat(sep=' ')}).first()
        return _to_aware(row[0]) if row and row[0] else None
    except Exception as exc:  # pragma: no cover — защитный код
        logger.error('access: paid lookup failed user=%s: %r', user_id, exc)
        return None


def _founder_expires_at(user_id: int, now: datetime) -> Optional[datetime]:
    """MAX(expires_at) по действующим выдачам Основателя (бесплатным)."""
    now_n = _naive_utc(now)
    try:
        from models_founders import FounderGrant
        rows = (FounderGrant.query
                .filter(FounderGrant.user_id == user_id,
                        FounderGrant.is_free_grant.is_(True))
                .all())
        best = None
        for g in rows:  # окно выдачи: starts_at <= now < expires_at
            starts = _to_aware(g.starts_at)
            ends = _to_aware(g.expires_at)
            if starts is None or ends is None:
                continue
            if starts <= now < ends and (best is None or ends > best):
                best = ends
        return best
    except Exception as exc:  # pragma: no cover — защитный код
        logger.error('access: founder lookup failed user=%s: %r', user_id, exc)
        return None


def _trial_expires_at(user) -> Optional[datetime]:
    trial_until = getattr(user, 'trial_until', None)
    ends = _to_aware(trial_until)
    if ends is None:
        return None
    return ends


# ─────────────────────────── resolve_access ───────────────────────────

def resolve_access(user, now: Optional[datetime] = None) -> Tuple[AccessSource, Optional[datetime]]:
    """(source, expires_at) — единая точка правды о доступе пользователя.

    `now` — aware UTC (для тестов); по умолчанию текущий момент.
    Пользователь без id (аноним) → ('free', None).
    """
    if user is None:
        return 'free', None
    uid = getattr(user, 'id', None)
    if uid is None:
        return 'free', None
    now = now or datetime.now(UTC)

    try:
        paid_end = _paid_expires_at(uid, now)
        if paid_end is not None:
            return 'paid', paid_end
        founder_end = _founder_expires_at(uid, now)
        if founder_end is not None:
            return 'founder', founder_end
        trial_end = _trial_expires_at(user)
        if trial_end is not None and trial_end > now:
            return 'trial', trial_end
    except Exception as exc:  # pragma: no cover — защитный код
        logger.error('access: resolve failed user=%s: %r', uid, exc)
        return 'free', None
    return 'free', None


def has_paid_access(user) -> bool:
    """True, если доступ не free (для method_week/paywall.py)."""
    source, _ = resolve_access(user)
    return source != 'free'


def msk_iso(dt: Optional[datetime]) -> Optional[str]:
    """ISO-строка по Москве — для интерфейса (resets_at и т.п.)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(MSK).isoformat()
