# -*- coding: utf-8 -*-
"""LIMITS_V1 — мягкие лимиты Free (services/limits.py).

Правила:
  * лимит действует ТОЛЬКО когда resolve_access = free И services.ab.apply_limits
    = True (режим experiment/rollout после PAYWALL_START_AT);
  * ключ дня — usage_date, вычисляет сервер через zoneinfo('Europe/Moscow');
    дату от клиента не принимаем;
  * списание — одна атомарная операция INSERT … ON CONFLICT (user_id, usage_date)
    DO UPDATE … WHERE c + n <= :limit RETURNING c (разделённые
    can_use_feature → выдача → increment_usage НЕ допускаются);
  * ИИ: сначала зарезервировать операцию разбора (try_consume), потом вызывать
    модель ВНЕ транзакции БД; при сбое вернуть резерв (refund);
  * при исключении БД задача выдаётся (fail-open), ошибка — в лог/Sentry;
  * сброс в 00:00 МСК; PAYWALL_MODE=off выключает немедленно.

Счётчики живут в существующей таблице usage_daily (user_id, date):
  'free_tasks' → tasks_completed, 'free_ai' → ai_explanations_used.
История не переписывается: существующие строки premium-учёта не трогаем
(у прежнего increment_usage дата UTC — оставляем как есть, лимит ведёт
свои записи по МСК; пересечения строк не ломают атомарность upsert'а).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from flask import g, jsonify, request
from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)
MSK = ZoneInfo('Europe/Moscow')
UTC = timezone.utc

FEATURE_COLUMN = {
    'free_tasks': 'tasks_completed',
    'free_ai': 'ai_explanations_used',
}


# ─────────────────────────── env ───────────────────────────

def free_tasks_per_day() -> int:
    # Free = 1 задача в день (28.10.2026). FREE_TASKS_PER_DAY в env — переопределить.
    try:
        return max(0, int(os.environ.get('FREE_TASKS_PER_DAY', '1')))
    except ValueError:
        return 1


def free_ai_per_day() -> int:
    try:
        return max(0, int(os.environ.get('FREE_AI_PER_DAY', '1')))
    except ValueError:
        return 1


def feature_limit(feature: str) -> int:
    return free_tasks_per_day() if feature == 'free_tasks' else free_ai_per_day()


# ─────────────────────────── ключ дня ───────────────────────────

def usage_date(now: Optional[datetime] = None) -> str:
    """Календарный день по МСК (YYYY-MM-DD). Сервер, не клиент."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(MSK).date().isoformat()


def resets_at_iso(now: Optional[datetime] = None) -> str:
    """ISO-момент следующей полуночи МСК (сброс лимита)."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    local = now.astimezone(MSK)
    next_midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return next_midnight.isoformat()


# ─────────────────────────── активность ───────────────────────────

# 2026-10-24: ГЛАВНЫЙ ВЫКЛЮЧАТЕЛЬ лимитов Free. 28.10.2026: лимиты
# ВКЛЮЧЕНЫ по умолчанию (Free = 1 задача и 1 ИИ-разбор в день).
# Аварийно выключить без деплоя: FREE_LIMITS_DISABLED=1 в env.
FREE_LIMITS_DISABLED = False  # read per-call in limits_active()


def _disabled_env() -> bool:
    """FREE_LIMITS_DISABLED проверяется на каждый вызов (не при импорте)."""
    v = os.environ.get('FREE_LIMITS_DISABLED', '')
    if not v:
        return False
    return v.strip().lower() in ('1', 'true', 'yes', 'on')


def limits_active(user, now: Optional[datetime] = None) -> bool:
    """Лимит действует: доступ free И эксперимент включил лимиты."""
    if _disabled_env():
        return False
    try:
        from services.access import resolve_access
        from services.ab import apply_limits
        if resolve_access(user, now=now)[0] != 'free':
            return False
        return bool(apply_limits(user, now=now))
    except Exception as exc:
        logger.error('limits: active check failed user=%s: %r (fail-open)',
                     getattr(user, 'id', None), exc)
        return False


# ─────────────────────────── атомарное списание ───────────────────────────

_idx_engines: set = set()


def _ensure_unique_index() -> None:
    """Уникальный индекс (user_id, date) на usage_daily. Таблицу создаёт
    миграция 002_add_subscriptions (обязательная) — здесь её не создаём,
    чтобы не плодить вторую схему. Если индекс не строится из-за дублей —
    пишем в лог (ручная чистка), списание уходит в fail-open."""
    try:
        engine_key = id(db.engine)
    except Exception:
        engine_key = None
    if engine_key is not None and engine_key in _idx_engines:
        return
    try:
        db.session.execute(text(
            'CREATE UNIQUE INDEX IF NOT EXISTS ux_usage_daily_user_date '
            'ON usage_daily (user_id, date)'))
        db.session.commit()
        if engine_key is not None:
            _idx_engines.add(engine_key)
    except Exception as exc:
        db.session.rollback()
        dup = None
        try:
            dup = db.session.execute(text(
                'SELECT COUNT(*) FROM (SELECT user_id, date FROM usage_daily '
                'GROUP BY user_id, date HAVING COUNT(*) > 1) t')).scalar()
        except Exception:
            pass
        logger.error('limits: unique index on usage_daily failed (duplicates=%s): %r',
                     dup, exc)


def try_consume(user_id: int, feature: str, limit: int, n: int = 1,
                day: Optional[str] = None) -> bool:
    """Атомарно списать n единиц. True — списано, False — лимит исчерпан.

    Исключение БД → True (fail-open: задача выдаётся, ошибка в лог).
    """
    col = FEATURE_COLUMN.get(feature)
    if col is None or n <= 0 or limit <= 0:
        return True  # неизвестная фича/нулевые параметры не блокируют
    day = day or usage_date()
    _ensure_unique_index()
    try:
        if db.engine.dialect.name == 'postgresql':
            sql = text(
                f'INSERT INTO usage_daily (user_id, date, {col}) VALUES (:u, :d, :n) '
                f'ON CONFLICT (user_id, date) DO UPDATE SET {col} = usage_daily.{col} + :n '
                f'WHERE usage_daily.{col} + :n <= :limit RETURNING {col}')
        else:
            sql = text(
                f'INSERT INTO usage_daily (user_id, date, {col}) VALUES (:u, :d, :n) '
                f'ON CONFLICT (user_id, date) DO UPDATE SET {col} = {col} + :n '
                f'WHERE {col} + :n <= :limit RETURNING {col}')
        res = db.session.execute(sql, {'u': user_id, 'd': day, 'n': n, 'limit': limit})
        row = res.fetchone()   # SQLite: курсор должен быть дочитан ДО commit
        db.session.commit()
        return row is not None
    except Exception as exc:
        db.session.rollback()
        logger.error('limits: try_consume failed user=%s feature=%s: %r (fail-open)',
                     user_id, feature, exc)
        _track_fail_open(user_id, feature)
        return True


def _track_fail_open(user_id: int, feature: str) -> None:
    """Событие limits_fail_open для дашборда запуска (сам tracking fail-open)."""
    try:
        from services import funnel
        funnel.track('limits_fail_open', {'feature': feature}, user_id=user_id)
    except Exception:  # noqa: BLE001
        pass


def remaining(user_id: int, feature: str, limit: int, day: Optional[str] = None) -> int:
    """Остаток на сегодня — только для показа, не для решений."""
    col = FEATURE_COLUMN.get(feature)
    if col is None:
        return 0
    day = day or usage_date()
    try:
        row = db.session.execute(text(
            f'SELECT {col} FROM usage_daily WHERE user_id = :u AND date = :d'),
            {'u': user_id, 'd': day}).first()
        used = int(row[0]) if row and row[0] else 0
        return max(0, limit - used)
    except Exception:
        return 0


def refund(user_id: int, feature: str, n: int = 1, day: Optional[str] = None) -> None:
    """Вернуть резерв при сбое (ИИ не ответил). Ниже нуля не опускаем."""
    col = FEATURE_COLUMN.get(feature)
    if col is None or n <= 0:
        return
    day = day or usage_date()
    # SQLite: MAX(a, b); PostgreSQL: GREATEST(a, b)
    floor_fn = 'GREATEST' if db.engine.dialect.name == 'postgresql' else 'MAX'
    try:
        db.session.execute(text(
            f'UPDATE usage_daily SET {col} = {floor_fn}(0, {col} - :n) '
            f'WHERE user_id = :u AND date = :d'),
            {'u': user_id, 'd': day, 'n': n})
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error('limits: refund failed user=%s feature=%s: %r', user_id, feature, exc)


# ─────────────────────────── контекст для маршрутов/шаблонов ───────────────────────────

def daily_context(user, now: Optional[datetime] = None) -> dict:
    """Единый контекст лимитов для get_daily_tasks и шаблонов."""
    active = limits_active(user, now=now)
    day = usage_date(now)
    tasks_limit = free_tasks_per_day()
    ai_limit = free_ai_per_day()
    uid = getattr(user, 'id', None) or 0
    ctx = {
        'active': active,
        'tasks_limit': tasks_limit,
        'tasks_remaining': tasks_limit,
        'ai_limit': ai_limit,
        'ai_remaining': ai_limit,
        'resets_at': resets_at_iso(now),
        'usage_date': day,
        'upgrade_url': '/subscribe?from=daily_limit',
    }
    if active and uid:
        ctx['tasks_remaining'] = remaining(uid, 'free_tasks', tasks_limit, day)
        ctx['ai_remaining'] = remaining(uid, 'free_ai', ai_limit, day)
    return ctx


# ─────────────────────────── хук ИИ-тьютора ───────────────────────────

def _tutor_dialog_started(user_id: int, agent_type: str) -> bool:
    """Диалог уже начат (есть сообщения пользователя в этом агенте)?
    Продолжение начатого диалога лимит НЕ расходует."""
    try:
        from models import ChatMessage
        return (ChatMessage.query
                .filter_by(user_id=user_id, agent_type=agent_type, role='user')
                .first() is not None)
    except Exception as exc:
        logger.error('limits: dialog check failed user=%s: %r (fail-open)', user_id, exc)
        return True  # при сомнении считаем продолжением — не блокируем


def install_limits_hooks(app) -> None:
    """POST /api/tutor/send: резерв разбора до вызова модели, возврат при сбое.
    Регистрируется из routes/__init__._install_limits (app.py не трогаем).
    Отключить: LIMITS_AUTOREG=0."""
    if app.extensions.get('limits_installed'):
        return
    app.extensions['limits_installed'] = True

    @app.before_request
    def _limits_ai_guard():
        if request.path != '/api/tutor/send' or request.method != 'POST':
            return None
        try:
            from flask_login import current_user
            if not getattr(current_user, 'is_authenticated', False):
                return None
            if not limits_active(current_user):
                return None
            if request.is_json:
                agent_type = (request.get_json(silent=True) or {}).get('agent_type', 'general')
            else:
                agent_type = request.form.get('agent_type', 'general')
            if _tutor_dialog_started(current_user.id, agent_type):
                return None  # продолжение начатого диалога
            if try_consume(current_user.id, 'free_ai', free_ai_per_day()):
                g.limits_ai_consumed = True   # резерв взят
                return None
            from services.ab import log_limit_shown
            log_limit_shown(current_user)
            return jsonify({
                'error': 'limit',
                'upgrade_url': '/subscribe?from=ai_limit',
                'resets_at': resets_at_iso(),
            }), 402
        except Exception as exc:  # fail-open: запрос идёт дальше
            logger.error('limits: ai guard error: %r', exc)
            return None

    @app.after_request
    def _limits_ai_refund(response):
        """Сбой модели (5xx) → возвращаем резерв."""
        try:
            if getattr(g, 'limits_ai_consumed', False) and response.status_code >= 500:
                from flask_login import current_user
                if getattr(current_user, 'is_authenticated', False):
                    refund(current_user.id, 'free_ai', 1)
                    g.limits_ai_consumed = False
        except Exception as exc:
            logger.error('limits: refund error: %r', exc)
        return response

    logger.info('LIMITS_V1 hooks installed (/api/tutor/send)')
