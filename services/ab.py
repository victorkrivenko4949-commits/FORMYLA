# -*- coding: utf-8 -*-
"""AB_V1 — A/B-группы эксперимента лимитов (services/ab.py).

Правила:
  * назначение — один раз, при первом обращении ПОДХОДЯЩЕГО пользователя
    после PAYWALL_START_AT в режиме experiment;
  * подходящий: resolve_access = 'free' (нет оплаченного доступа, бесплатного
    доступа Основателя, триала) и нет ручного исключения (AB_EXCLUDE_USER_IDS);
    условие одинаково для обеих групп;
  * группа = sha256(f"{experiment_id}:{user_id}") → int % 100 < PAYWALL_AB
    (встроенный hash() НЕ используется — он не стабилен между запусками из-за
    PYTHONHASHSEED);
  * INSERT … ON CONFLICT DO NOTHING — конкурентные первые обращения дают
    одну строку;
  * в режиме off назначения не создаются;
  * смена PAYWALL_AB не переносит людей задним числом (строка уже есть);
  * покупка после назначения снимает лимит, но человек остаётся в своей
    группе для анализа;
  * ошибка назначения → apply_limits = False (fail-open: лимит не применяется).

События (через services.funnel.track, отдельные):
  ab_assigned, ab_first_eligible_request, limit_applied, limit_shown.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)

ALGO_VERSION = 'sha256_mod100_v1'
COHORTS = ('limits', 'control')


# ─────────────────────────── env ───────────────────────────

def mode() -> str:
    """off | experiment | rollout. Дефолт — off (безопасно)."""
    return (os.environ.get('PAYWALL_MODE', 'off') or 'off').strip().lower()


def start_at() -> datetime:
    """PAYWALL_START_AT → aware UTC (дефолт 03.11.2026 00:00 МСК)."""
    raw = (os.environ.get('PAYWALL_START_AT') or '2026-11-02T21:00:00Z').strip().replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        logger.error('ab: bad PAYWALL_START_AT=%r', raw)
        dt = datetime(2026, 10, 31, 21, 0, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def experiment_id() -> str:
    return (os.environ.get('PAYWALL_EXPERIMENT_ID') or 'limits_v1').strip() or 'limits_v1'


def admin_preview() -> bool:
    """PAYWALL_PREVIEW_ADMINS=1 — предпросмотр платной версии ТОЛЬКО для
    админов (is_admin: user_id=1 / Victor / nickname 'lavrik') при
    PAYWALL_MODE=off. Обычные пользователи не затронуты."""
    return (os.environ.get('PAYWALL_PREVIEW_ADMINS', '0') or '0').strip() == '1'


def _admin_preview_applies(user) -> bool:
    """Предпросмотр: админ И доступ free (платный доступ лимитами не трогаем)."""
    if not admin_preview():
        return False
    try:
        if not getattr(user, 'is_admin', False):
            return False
        from services.access import resolve_access
        return resolve_access(user)[0] == 'free'
    except Exception as exc:  # noqa: BLE001
        logger.error('ab: admin preview check failed: %r', exc)
        return False


def ab_percent() -> int:
    try:
        return max(0, min(100, int(os.environ.get('PAYWALL_AB', '50'))))
    except (TypeError, ValueError):
        return 50


def _excluded_ids() -> set:
    out = set()
    for part in (os.environ.get('AB_EXCLUDE_USER_IDS') or '').split(','):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


# ─────────────────────────── группа ───────────────────────────

def cohort_for(exp_id: str, user_id: int, percent: Optional[int] = None) -> str:
    """Детерминированная группа: sha256(exp:user) → int % 100 < percent."""
    percent = ab_percent() if percent is None else percent
    digest = hashlib.sha256(f'{exp_id}:{user_id}'.encode('utf-8')).hexdigest()
    return 'limits' if int(digest, 16) % 100 < percent else 'control'


# ─────────────────────────── назначение ───────────────────────────

def _is_eligible(user, now: datetime) -> bool:
    """Подходящий пользователь: доступ free и нет ручного исключения."""
    uid = getattr(user, 'id', None)
    if uid is None or uid in _excluded_ids():
        return False
    try:
        from services.access import resolve_access
        source, _ = resolve_access(user, now=now)
        return source == 'free'
    except Exception as exc:
        logger.error('ab: eligibility check failed user=%s: %r', uid, exc)
        return False


def get_cohort(user_id: int, exp_id: Optional[str] = None) -> Optional[str]:
    """Уже назначенная группа (без создания)."""
    from models_ab import AbCohort
    row = (AbCohort.query
           .filter_by(experiment_id=exp_id or experiment_id(), user_id=user_id).first())
    return row.cohort if row else None


def assign_cohort(user, now: Optional[datetime] = None, create_events: bool = True) -> Optional[str]:
    """Назначить группу (один раз) и вернуть 'limits'|'control' или None.

    None = не назначается (не подходит / off / до старта / ошибка записи).
    Идемпотентно: существующая строка не перезаписывается.
    """
    now = now or datetime.now(timezone.utc)
    uid = getattr(user, 'id', None)
    if uid is None:
        return None
    exp = experiment_id()
    try:
        existing = get_cohort(uid, exp)
    except Exception as exc:  # ошибка чтения — не роняем запрос, fail-open ниже
        logger.error('ab: get_cohort failed user=%s: %r', uid, exc)
        return None
    if existing:
        return existing

    if mode() != 'experiment':
        return None
    if now < start_at():
        return None
    if not _is_eligible(user, now):
        return None

    cohort = cohort_for(exp, uid)
    try:
        if db.engine.dialect.name == 'postgresql':
            sql = ("INSERT INTO ab_cohort (experiment_id, user_id, cohort, assigned_at, "
                   "eligible_at, algo_version) VALUES (:e, :u, :c, :a, :a, :v) "
                   "ON CONFLICT DO NOTHING")
        else:
            sql = ("INSERT OR IGNORE INTO ab_cohort (experiment_id, user_id, cohort, assigned_at, "
                   "eligible_at, algo_version) VALUES (:e, :u, :c, :a, :a, :v)")
        res = db.session.execute(text(sql), {
            'e': exp, 'u': uid, 'c': cohort,
            'a': now.replace(tzinfo=None), 'v': ALGO_VERSION})
        db.session.commit()
        inserted = bool(getattr(res, 'rowcount', 0))
    except Exception as exc:
        db.session.rollback()
        logger.error('ab: assignment failed user=%s: %r (fail-open, лимит не применяется)', uid, exc)
        return None

    if inserted and create_events:
        _track('ab_assigned', uid, {'experiment_id': exp, 'cohort': cohort})
        _track('ab_first_eligible_request', uid, {'experiment_id': exp})
    # конкурентный первый запрос: строку вставил другой поток
    return get_cohort(uid, exp) or cohort


# ─────────────────────────── применение лимита ───────────────────────────

def apply_limits(user, now: Optional[datetime] = None) -> bool:
    """Применять ли мягкие лимиты к пользователю.

    - PAYWALL_MODE=off или старт ещё не наступил → False;
    - rollout → True для всех free, группы не трогаются;
    - experiment → True только для cohort=limits (назначение при первом
      подходящем обращении);
    - покупка после назначения снимает лимит (resolve_access != free),
      человек остаётся в группе для анализа;
    - ошибка назначения → False (fail-open).
    """
    m = mode()
    if m not in ('experiment', 'rollout'):
        # off: предпросмотр для админов (PAYWALL_PREVIEW_ADMINS=1),
        # старт-дата на предпросмотр НЕ влияет — он и нужен ДО 03.11
        return _admin_preview_applies(user)
    now = now or datetime.now(timezone.utc)
    if now < start_at():
        return False
    try:
        from services.access import resolve_access
        source, _ = resolve_access(user, now=now)
        if source != 'free':
            return False
    except Exception as exc:
        logger.error('ab: resolve_access failed user=%s: %r (fail-open)', getattr(user, 'id', None), exc)
        return False
    if m == 'rollout':
        return True
    try:
        cohort = assign_cohort(user, now=now)
    except Exception as exc:  # ошибка назначения → лимит не применяется (fail-open)
        logger.error('ab: assignment error user=%s: %r', getattr(user, 'id', None), exc)
        return False
    return bool(cohort) and cohort == 'limits'


# ─────────────────────────── события и метки ───────────────────────────

def _track(event: str, user_id: int, props: dict) -> None:
    try:
        from services import funnel
        funnel.track(event, props, user_id=user_id)
    except Exception as exc:  # событие не должно ломать запрос
        logger.debug('ab: funnel.track(%s) failed: %r', event, exc)


def log_limit_applied(user) -> None:
    """Событие «применение лимита» (вызывается при отклонении запроса лимитом)."""
    uid = getattr(user, 'id', None)
    if uid is not None:
        _track('limit_applied', uid, {'experiment_id': experiment_id()})


def log_limit_shown(user) -> None:
    """Событие «показ экрана лимита» + отметка first_limit_shown_at."""
    uid = getattr(user, 'id', None)
    if uid is None:
        return
    exp = experiment_id()
    _track('limit_shown', uid, {'experiment_id': exp})
    try:
        if db.engine.dialect.name == 'postgresql':
            sql = ("UPDATE ab_cohort SET first_limit_shown_at = :now "
                   "WHERE experiment_id = :e AND user_id = :u AND first_limit_shown_at IS NULL")
        else:
            sql = ("UPDATE ab_cohort SET first_limit_shown_at = :now "
                   "WHERE experiment_id = :e AND user_id = :u AND first_limit_shown_at IS NULL")
        db.session.execute(text(sql), {'now': datetime.utcnow(), 'e': exp, 'u': uid})
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.debug('ab: mark first_limit_shown failed user=%s: %r', uid, exc)
