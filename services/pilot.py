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
from datetime import datetime, timedelta
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


# ── Расписание занятий недели (для баннера пилота) ───────────────────────────

def pilot_session_today(user_id: int) -> dict:
    """Какое сегодня занятие по тарифу пилотного аккаунта.

    «Работяга» (6 занятий, Пн–Сб): 1 пробник (Сб), 1 метод (Ср),
    4 задачи дня (Пн, Вт, Чт, Пт). Вс — отдых.
    «Спокойный» (3 занятия, Пн/Ср/Пт): метод раз в 2 недели (Ср нечётных
    недель), пробник раз в 2 недели (Пт нечётных недель), иначе задачи.

    Никогда не бросает. Возвращает dict(week, session_index, session_type,
    session_label, plan) или {'enabled': False}.
    """
    out = {'enabled': False}
    try:
        from datetime import datetime, timedelta
        from services.subscription import get_subscription_service
        plan = get_subscription_service().get_user_plan(user_id)
        variant = plan.get('plan') if plan.get('is_premium') else None
        if variant not in PILOT_PLANS:
            return out

        started = None
        try:
            row = None
            from sqlalchemy import text as _t
            row = __import__('models').db.session.execute(_t(
                'SELECT started_at FROM subscriptions '
                'WHERE user_id = :u AND status = :s ORDER BY id DESC LIMIT 1'),
                {'u': user_id, 's': 'active'}).first()
            if row and row[0]:
                started = row[0]
        except Exception:
            pass
        if started is None:
            started = datetime.utcnow()

        now = datetime.utcnow()
        days_in = max(0, (now - started).days)
        week = days_in // 7 + 1
        weekday = now.weekday()  # 0=Пн … 6=Вс

        # Первая неделя — диагностическая: без методов и пробников,
        # только тест (5 задач) и задачи дня соответствующего уровня.
        # (См. план Premium: «на первой неделе нет пробника и методов».)
        if week == 1:
            if weekday == 6:
                session_type, session_index = 'rest', None
            else:
                session_type, session_index = 'diagnostic', None
            out = {
                'enabled': True,
                'plan': variant,
                'week': week,
                'session_type': session_type,
                'session_index': session_index,
                'total': 6 if variant == 'premium_intense' else 3,
                'session_label': 'диагностическая неделя: тест + задачи дня',
            }
            return out

        if variant == 'premium_intense':
            schedule = {0: 'tasks', 1: 'tasks', 2: 'method', 3: 'tasks',
                        4: 'tasks', 5: 'mock', 6: 'rest'}
            order = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6}
            total = 6
            session_type = schedule.get(weekday, 'rest')
            session_index = order.get(weekday)
        else:  # premium_calm
            total = 3
            if weekday not in (0, 2, 4):
                session_type, session_index = 'rest', None
            else:
                odd_week = (week % 2 == 1)
                if weekday == 2 and odd_week:
                    session_type = 'method'
                elif weekday == 4 and not odd_week:
                    session_type = 'mock'
                else:
                    session_type = 'tasks'
                session_index = {0: 1, 2: 2, 4: 3}[weekday]

        labels = {
            'tasks': 'задачи дня',
            'method': 'метод (70% теория + 3 задачи)',
            'mock': 'пробник — реальный вариант прошлых лет',
            'rest': 'выходной',
        }
        out = {
            'enabled': True,
            'plan': variant,
            'week': week,
            'session_type': session_type,
            'session_index': session_index,
            'total': total,
            'session_label': labels.get(session_type, ''),
        }
    except Exception as e:
        logger.warning('[PILOT] session_today failed: %s', e)
    return out


# ── Анонс Premium (3 ноября 2026, 19:00 МСК) ────────────────────────────────

PREMIUM_LAUNCH_AT_UTC = datetime(2026, 11, 3, 16, 0, 0)  # 19:00 МСК = 16:00 UTC

PREMIUM_LAUNCH_BODY = (
    "У FORMYLA появилась Premium-версия! 🎓\n"
    "\n"
    "Что внутри: генератор чертежей, ИИ-тьютор-куратор, персональные задачи дня "
    "под конкретную олимпиаду (в каталоге их 12) и 102 метода — ключ к успеху.\n"
    "\n"
    "Два формата:\n"
    "🔥 «Работяга» — 6 занятий в неделю (800 ₽/мес): 4 задачи дня, 1 метод и "
    "1 пробник реального варианта прошлых лет\n"
    "😌 «Спокойный» — 3 занятия в неделю (500 ₽/мес): то же самое, но в 2 раза "
    "медленнее\n"
    "\n"
    "Подробнее и выбрать тариф: /subscribe"
)


def ensure_premium_launch_notice() -> bool:
    """Идемпотентно создаёт ЧЕРНОВИК анонса Premium (3 ноября, 19:00 МСК).

    Заметка создаётся НЕАКТИВНОЙ (active=FALSE): включить её решает
    владелец (кнопка «Активировать» в /admin/notices) — глобальный показ
    всем пользователям требует явного подтверждения. Пока действует
    ограничение пилота «всё в двух аккаунтах».
    Никогда не бросает. Возвращает True, если заметка создана сейчас.
    """
    try:
        from models import db
        from sqlalchemy import text
        # 1) гарантируем таблицу И колонку activate_at ДО поиска записи
        try:
            db.session.execute(text(
                "CREATE TABLE IF NOT EXISTS admin_notices ("
                "  id SERIAL PRIMARY KEY, title VARCHAR(160) NOT NULL,"
                "  body TEXT NOT NULL, link_url VARCHAR(500), link_text VARCHAR(120),"
                "  targets TEXT, active BOOLEAN NOT NULL DEFAULT TRUE,"
                "  activate_at TIMESTAMP, created_by INTEGER,"
                "  created_at TIMESTAMP NOT NULL DEFAULT NOW())"))
        except Exception:
            pass
        try:
            from routes.admin_notices import _ensure_activate_at_column
            _ensure_activate_at_column()
        except Exception:
            try:
                db.session.execute(text(
                    'ALTER TABLE admin_notices ADD COLUMN activate_at TIMESTAMP'))
                db.session.commit()
            except Exception:
                db.session.rollback()
        # 2) ищем существующую заметку
        row = db.session.execute(text(
            'SELECT id FROM admin_notices WHERE body LIKE :frag LIMIT 1'),
            {'frag': '%Premium-версия!%'}).first()
        if row:
            return False
        # 3) создаём ЧЕРНОВИК: active=FALSE, включит владелец через админку
        db.session.execute(text(
            'INSERT INTO admin_notices (title, body, link_url, link_text, '
            'targets, active, activate_at, created_by, created_at) '
            'VALUES (:t, :b, :l, :lt, NULL, FALSE, :aa, NULL, NOW())'),
            {'t': '🎓 Куратор', 'b': PREMIUM_LAUNCH_BODY,
             'l': '/subscribe', 'lt': 'Посмотреть тарифы',
             'aa': PREMIUM_LAUNCH_AT_UTC})
        db.session.commit()
        logger.info('[PILOT] premium launch notice DRAFT created (inactive, '
                    'activates %s UTC once owner enables it)',
                    PREMIUM_LAUNCH_AT_UTC.isoformat())
        return True
    except Exception as e:
        logger.warning('[PILOT] launch notice failed: %s', e)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        return False
