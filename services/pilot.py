# -*- coding: utf-8 -*-
"""services/pilot.py — пилот Premium-версии на двух аккаунтах.

Пилот: новые тарифы (premium_intense / premium_calm) и новый премиум-контент
видны только пилотным аккаунтам. Для всех остальных пользователей сайт работает
как раньше — ничего не меняется.

Пилотные аккаунты (по id в БД):
  * victor  (id=1)  — владелец (без бесплатной беты — проверка оплаты)
  * Lavrik  (id=5)
  * Damian  (id=7452)

Дополнительно — email-пилоты (PILOT_EMAILS ниже): доступ по email, без знания
id в БД. Используется, чтобы открыть покупку тарифов конкретному аккаунту
до общего старта. Для email из PILOT_REVOKE_BETA_EMAILS бесплатная бета
не выдаётся — доступ только после реальной оплаты.

Включение/выключение пилота целиком — флагом PILOT_ENABLED ниже.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger('formyla.pilot')

# ── Конфигурация пилота ─────────────────────────────────────────────────────

PILOT_ENABLED = True

# id пилотных аккаунтов: victor=1, Lavrik=5, Damian=7452
PILOT_USER_IDS = (1, 5, 7452)

# Email-пилоты: доступ по email (без знания id в БД) — для аккаунтов,
# которым открываем покупку тарифов до 3 ноября. Проверка регистронезависимая.
PILOT_EMAILS = ('viktorformulevitch@yandex.ru',)

# Пилотные id, которым НЕ выдаётся бесплатная бета, а активная бета
# (is_beta_access = TRUE) снимается на старте. Оплаченные подписки не трогаются.
# После проверки оплаты — сделать пустым: ()
PILOT_REVOKE_BETA_IDS = (1,)

# Пилотные email без бесплатной беты (аналог PILOT_REVOKE_BETA_IDS):
# доступ к Premium — только после реальной оплаты.
PILOT_REVOKE_BETA_EMAILS = ('viktorformulevitch@yandex.ru',)

# Пилотные тарифы (см. services/subscription.py → PLAN_LIMITS)
PILOT_PLANS = ('premium_intense', 'premium_calm')

# Тариф, который активируется пилотным аккаунтам по умолчанию (бета, без оплаты)
PILOT_DEFAULT_PLAN = 'premium_intense'

# Открытая продажа (владелец, 03.11.2026): покупка тарифов «Работяга»/
# «Спокойный» доступна ВСЕМ зарегистрированным, не только пилотным
# аккаунтам. False возвращает ограничение «до старта» — тогда чекаут
# снова открыт только пилотам (и подаркам для детей).
PILOT_OPEN_SALES = True


# ── Хелперы ─────────────────────────────────────────────────────────────────

def _norm_email(email) -> str:
    return (email or '').strip().lower()


def _pilot_emails() -> set:
    return {e.strip().lower() for e in PILOT_EMAILS if e.strip()}


def _revoke_beta_emails() -> set:
    return {e.strip().lower() for e in PILOT_REVOKE_BETA_EMAILS if e.strip()}


def _email_for_user_id(user_id) -> str:
    """Email аккаунта по id. Ошибки БД / нет аккаунта → ''.

    Нужен для email-пилотов, когда на входе только id (например,
    current_user.id в маршрутах оплаты): без запроса email не проверить.
    """
    try:
        from models import User
        row = User.query.get(int(user_id))
        return _norm_email(getattr(row, 'email', None))
    except Exception:  # noqa: BLE001
        return ''


def _user_id_for_email(email) -> Optional[int]:
    """id аккаунта по email (регистронезависимо). Ошибки БД / нет такого → None."""
    if not email:
        return None
    try:
        from sqlalchemy import func
        from models import User
        row = (User.query
               .filter(func.lower(User.email) == _norm_email(email))
               .first())
        return int(row.id) if row is not None else None
    except Exception:  # noqa: BLE001
        return None


def _is_pilot_email(email) -> bool:
    """True, если email входит в PILOT_EMAILS (регистронезависимо)."""
    if not PILOT_ENABLED:
        return False
    return _norm_email(email) in _pilot_emails()


def is_pilot_user(user) -> bool:
    """True, если user (объект User или id) — пилотный аккаунт и пилот включён.

    Пилот = id из PILOT_USER_IDS ИЛИ email из PILOT_EMAILS.
    Безопасен для анонимных пользователей (None → False).
    """
    if not PILOT_ENABLED:
        return False
    try:
        if user is None:
            return False
        # Объект User: проверяем id и email (email — без запроса в БД)
        user_id = getattr(user, 'id', None)
        if user_id is not None:
            if int(user_id) in PILOT_USER_IDS:
                return True
            if _is_pilot_email(getattr(user, 'email', None)):
                return True
            if not _pilot_emails():
                return False
            # email на объекте пуст (аноним) — сверяем id по БД
            return _email_for_user_id(user_id) in _pilot_emails()
        if isinstance(user, int):
            if user in PILOT_USER_IDS:
                return True
            if not _pilot_emails():
                return False
            return _email_for_user_id(user) in _pilot_emails()
    except Exception:
        return False
    return False


def has_premium_access(user) -> bool:
    """Полный Premium-продукт (поток занятий, куратор-чат, навигация):
    аккаунт из пилотного списка ИЛИ активная подписка на пилотный тариф
    (бета / оплаченная / пробный день). После открытия продажи 03.11.2026
    доступ следует за тарифом: купил «Работяга»/«Спокойный» — получил
    продукт, даже если аккаунт не в пилотном списке.

    Безопасен для анонимов (None → False). Ошибки БД → False.
    """
    if is_pilot_user(user):
        return True
    uid = getattr(user, 'id', None) or user
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return False
    try:
        from models import db
        from sqlalchemy import text
        row = db.session.execute(text(
            "SELECT 1 FROM subscriptions "
            "WHERE user_id = :uid AND status = 'active' "
            "  AND (expires_at IS NULL OR expires_at > :now) "
            "  AND plan IN ('premium_intense', 'premium_calm') LIMIT 1"),
            {'uid': uid, 'now': datetime.utcnow().isoformat()}).fetchone()
        return row is not None
    except Exception:  # noqa: BLE001
        return False


def is_pilot_id(user_id) -> bool:
    """True, если user_id — пилотный id (или id email-пилота) и пилот включён."""
    if not PILOT_ENABLED:
        return False
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    if uid in PILOT_USER_IDS:
        return True
    if not _pilot_emails():
        return False
    return _email_for_user_id(uid) in _pilot_emails()


def can_take_theme_test(user) -> bool:
    """True — пользователь может проходить тест по теме дня (срез).

    Тест — функция Premium (владелец, 01.11.2026): доступен пилотным
    аккаунтам и пользователям с активной Premium-подпиской — пилотной
    бетой, оплаченной или бесплатным пробным днём на 24 часа.
    Бесплатным аккаунтам тест закрыт; задачи дня при этом тестом
    не блокируются (см. daily_tasks/routes.py, pick_daily_set).
    """
    if is_pilot_user(user):
        return True
    try:
        if user is None:
            return False
        return bool(user.has_active_subscription())
    except Exception:
        return False


# ── Активация бета-подписки для пилотных аккаунтов ─────────────────────────

def ensure_pilot_subscriptions() -> bool:
    """Идемпотентно выдаёт пилотным аккаунтам бета-Premium.

    Вызывается на старте приложения (после auto_migrate). Для каждого
    пилотного id: если нет активной подписки — активирует PILOT_DEFAULT_PLAN
    с is_beta=True (без оплаты). Существующие подписки не трогает.
    Для id из PILOT_REVOKE_BETA_IDS — снимает активную бета-подписку (не оплаченную)
    и бету им не выдаёт.

    Атомарность: успешный commit → True; любая ошибка → rollback и False.
    Никогда не бросает исключение наружу (пилот не должен ронять старт).
    """
    if not PILOT_ENABLED:
        return False
    try:
        from models import db as _models_db
        from sqlalchemy import text as _text
        from services.subscription import get_subscription_service
        svc = get_subscription_service()
        dirty = False
        # id email-пилотов (по users.email); revoke-email — без бесплатной беты
        email_pilot_ids: set = set()
        revoke_ids = set(PILOT_REVOKE_BETA_IDS)
        for email in _pilot_emails():
            uid = _user_id_for_email(email)
            if not uid:
                logger.info('[PILOT] email %s: аккаунт не найден — пропускаем', email)
                continue
            email_pilot_ids.add(uid)
            if email in _revoke_beta_emails():
                revoke_ids.add(uid)
        all_pilot_ids = set(PILOT_USER_IDS) | email_pilot_ids
        for rid in sorted(revoke_ids):
            try:
                res = _models_db.session.execute(_text(
                    "UPDATE subscriptions SET status = 'cancelled' "
                    "WHERE user_id = :u AND status = 'active' AND is_beta_access = TRUE"),
                    {'u': rid})
                if res.rowcount:
                    still = svc.get_user_plan(rid)
                    if not still.get('is_premium'):
                        _models_db.session.execute(_text(
                            "UPDATE users SET current_plan = 'free', plan_expires_at = NULL "
                            "WHERE id = :u"), {'u': rid})
                    dirty = True
                    logger.info('[PILOT] user %s: beta subscription revoked', rid)
            except Exception as e:
                logger.warning('[PILOT] user %s: beta revoke failed: %s', rid, e)
                try:
                    _models_db.session.rollback()
                except Exception:
                    pass
        for user_id in sorted(all_pilot_ids):
            if user_id in revoke_ids:
                continue  # без бесплатной беты — доступ только после оплаты
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

    «Работяга» (6 занятий): 1 пробник (последний день недели), 1 метод
    (средний день), остальные дни — задачи дня. Вс — отдых.
    «Спокойный» (3 занятия): метод раз в 2 недели (средний день нечётных
    недель), пробник раз в 2 недели (последний день чётных недель).

    PILOT_SCHEDULE_DAYS_V1 (03.11.2026): конкретные дни недели — ВЫБРАННЫЕ
    пользователем на /schedule (services/schedule_days.py). Пока выбор не
    сделан — прежние расписания по умолчанию (Пн–Сб / Пн-Ср-Пт).

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

        # PILOT_SCHEDULE_DAYS_V1: выбранные пользователем дни (может не быть)
        try:
            from services.schedule_days import days_for_plan as _days_for
            chosen = _days_for(user_id, variant)
        except Exception:
            chosen = None

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
        # Raw-SQL без типизации может вернуть строку (SQLite) — парсим
        if isinstance(started, str):
            started = datetime.fromisoformat(started[:19])

        now = datetime.utcnow()
        days_in = max(0, (now - started).days)
        week = days_in // 7 + 1
        weekday = now.weekday()  # 0=Пн … 6=Вс

        # Дни недели расписания: выбранные на /schedule или дефолт тарифа
        # (PILOT_SCHEDULE_DAYS_V1)
        if chosen:
            days_list = list(chosen)
        elif variant == 'premium_intense':
            days_list = [0, 1, 2, 3, 4, 5]   # Пн–Сб
        else:
            days_list = [0, 2, 4]             # Пн/Ср/Пт

        if week == 1:
            # Первая неделя — диагностическая: без методов и пробников,
            # только тест (5 задач) и задачи дня соответствующего уровня.
            # (См. план Premium: «на первой неделе нет пробника и методов».)
            # Диагностическая неделя — занятия только по дням расписания
            if weekday == 6 or weekday not in days_list:
                session_type, session_index = 'rest', None
            else:
                session_type, session_index = 'diagnostic', None
            out = {
                'enabled': True,
                'plan': variant,
                'week': week,
                'session_type': session_type,
                'session_index': session_index,
                'total': len(days_list),
                'session_label': 'диагностическая неделя: тест + задачи дня',
            }
            return out

        if variant == 'premium_intense':
            # Пробник убран из ротации (владелец, 03.11.2026, #176):
            # метод — в средний выбранный день, остальные дни — задачи дня.
            total = len(days_list)  # 6
            if weekday not in days_list:
                session_type, session_index = 'rest', None
            else:
                pos = days_list.index(weekday) + 1  # 1..6
                if pos == 3:
                    session_type = 'method'   # средний день (как Ср в дефолте)
                else:
                    session_type = 'tasks'
                session_index = pos
        else:  # premium_calm
            total = len(days_list)  # 3
            if weekday not in days_list:
                session_type, session_index = 'rest', None
            else:
                pos = days_list.index(weekday) + 1  # 1..3
                odd_week = (week % 2 == 1)
                if pos == 2 and odd_week:
                    session_type = 'method'
                else:
                    session_type = 'tasks'
                session_index = pos

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
