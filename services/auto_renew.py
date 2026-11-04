# -*- coding: utf-8 -*-
"""
services/auto_renew.py — AUTO_RENEW_V1 (27.10.2026): автопродление Premium.

Модель подписки:
  * Первый платёж тарифа Premium создаётся с save_payment_method=true —
    ЮKassa сохраняет способ оплаты, мы сохраняем payment_method.id
    (связку user_id ↔ payment_method_id, без реквизитов карты).
  * У пользователя появляется соглашение premium_auto_renewals: тариф,
    цена, способ оплаты, next_charge_at = дата окончания подписки.
  * Джоба из app.py (каждый час) проводит безакцептное списание через
    payment_method_id и продлевает подписку на 30 дней ОТ ДАТЫ ОКОНЧАНИЯ —
    оплаченные дни не сгорают. Списание проходит в окне 2 часов до
    конца периода (чтобы доступ не прерывался между списаниями).
    Аварийный стоп-кран: PREMIUM_AUTORENEW_ENABLED=0.
  * Отключение автопродления в один клик: доступ сохраняется до конца
    оплаченного периода. Отмена подписки тоже выключает автопродление.
  * Неудачное списание не отнимает оплаченные дни: 3 неудачные попытки
    (с паузой в 24 часа) → автопродление выключается.

Идемпотентность:
  * Одна попытка на оплачиваемый период: UNIQUE(renewal_id, period_start).
  * order_id = Idempotence-Key: повтор джобы не создаёт второй платёж.
  * Применение результата ровно один раз: атомарный перевод статуса
    попытки pending → applying (два воркера не продлят дважды).

Требования ЮKassa (см. доку recurring-payments): для автоплатежей
опция должна быть включена менеджером ЮKassa для магазина; пользователь
информируется об условиях (каждые 30 дней, как отключить) на странице
оплаты. Работает с картами, СБП, SberPay, T-Pay.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timedelta

import requests
from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)

YOOKASSA_API_BASE = "https://api.yookassa.ru/v3"
RENEWAL_WINDOW = timedelta(hours=2)   # списание не раньше чем за 2ч до конца
RETRY_PAUSE = timedelta(hours=24)    # пауза между неудачными попытками
MAX_FAILS = 3                        # после 3 отказов — выключить автопродление

_TABLES_ENSURED = False


def _now() -> datetime:
    return datetime.utcnow()


def _to_dt(v) -> datetime:
    """Значение даты из БД → naive datetime (SQLite хранит строками)."""
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if v is None:
        return None
    return datetime.fromisoformat(str(v))


def ensure_tables() -> None:
    """Создать таблицы автопродления (идемпотентно, PG и SQLite)."""
    global _TABLES_ENSURED
    if _TABLES_ENSURED:
        return
    try:
        engine_name = db.engine.dialect.name
        is_pg = engine_name == "postgresql"
        with db.engine.begin() as conn:
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS premium_auto_renewals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    plan VARCHAR(64) NOT NULL,
                    price_rub NUMERIC(10, 2) NOT NULL,
                    payment_method_id VARCHAR(128),
                    method_label VARCHAR(64),
                    enabled INTEGER NOT NULL DEFAULT 1,
                    next_charge_at TIMESTAMP,
                    fail_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
                if not is_pg else
                """
                CREATE TABLE IF NOT EXISTS premium_auto_renewals (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE,
                    plan VARCHAR(64) NOT NULL,
                    price_rub NUMERIC(10, 2) NOT NULL,
                    payment_method_id VARCHAR(128),
                    method_label VARCHAR(64),
                    enabled INTEGER NOT NULL DEFAULT 1,
                    next_charge_at TIMESTAMP,
                    fail_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            ))
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS premium_renewal_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    renewal_id INTEGER NOT NULL,
                    period_start TIMESTAMP NOT NULL,
                    period_end TIMESTAMP NOT NULL,
                    order_id VARCHAR(64) UNIQUE NOT NULL,
                    payment_id VARCHAR(128),
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (renewal_id, period_start)
                )
                """
                if not is_pg else
                """
                CREATE TABLE IF NOT EXISTS premium_renewal_attempts (
                    id SERIAL PRIMARY KEY,
                    renewal_id INTEGER NOT NULL,
                    period_start TIMESTAMP NOT NULL,
                    period_end TIMESTAMP NOT NULL,
                    order_id VARCHAR(64) UNIQUE NOT NULL,
                    payment_id VARCHAR(128),
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (renewal_id, period_start)
                )
                """
            ))
        _TABLES_ENSURED = True
    except Exception as e:  # noqa: BLE001
        logger.warning('[auto_renew] ensure_tables warning: %r', e)


def _yk_cfg() -> dict:
    try:
        from routes.yookassa_pay import get_yookassa_config
        return get_yookassa_config()
    except Exception as e:  # noqa: BLE001
        logger.warning('[auto_renew] yk config failed: %r', e)
        return {'configured': False, 'shop_id': '', 'secret_key': ''}


def _row_to_renewal(row) -> dict:
    if not row:
        return None
    keys = ('id', 'user_id', 'plan', 'price_rub', 'payment_method_id',
            'method_label', 'enabled', 'next_charge_at', 'fail_count')
    return dict(zip(keys, row)) if not isinstance(row, dict) else row


def get_auto_renewal(user_id: int) -> dict:
    """Соглашение об автопродлении пользователя (или None)."""
    ensure_tables()
    row = db.session.execute(text(
        "SELECT id, user_id, plan, price_rub, payment_method_id, method_label,"
        " enabled, next_charge_at, fail_count FROM premium_auto_renewals"
        " WHERE user_id = :uid LIMIT 1"
    ), {'uid': user_id}).fetchone()
    return _row_to_renewal(row)


def set_enabled(user_id: int, enabled: bool) -> bool:
    """Включить/выключить автопродление (доступ не трогает)."""
    ensure_tables()
    try:
        db.session.execute(text(
            "UPDATE premium_auto_renewals SET enabled = :en, fail_count = 0,"
            " updated_at = :now WHERE user_id = :uid"
        ), {'en': 1 if enabled else 0, 'now': _now(), 'uid': user_id})
        db.session.commit()
        return True
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[auto_renew] set_enabled failed: %r', e)
        return False


def upsert_from_payment(user_id: int, payment_id: str, plan: str) -> dict:
    """Сохранить способ оплаты с успешного первого платежа и создать соглашение.

    Проверяем платёж напрямую в API ЮKassa (защита от подделки):
    списание прошло и payment_method.saved == true. Иначе автопродление
    не подключаем (возвращаем connected=False).
    """
    ensure_tables()
    cfg = _yk_cfg()
    if not cfg.get('configured'):
        return {'connected': False, 'reason': 'not_configured'}
    if not payment_id or str(payment_id).startswith('demo_'):
        return {'connected': False, 'reason': 'demo_payment'}

    try:
        resp = requests.get(
            f"{YOOKASSA_API_BASE}/payments/{payment_id}",
            auth=(cfg['shop_id'], cfg['secret_key']), timeout=10,
        )
        if resp.status_code != 200:
            return {'connected': False, 'reason': f'lookup HTTP {resp.status_code}'}
        p = resp.json() or {}
    except Exception as e:  # noqa: BLE001
        logger.warning('[auto_renew] payment lookup failed: %r', e)
        return {'connected': False, 'reason': 'lookup_failed'}

    if p.get('status') != 'succeeded' or not p.get('paid'):
        return {'connected': False, 'reason': 'not_paid'}
    pm = p.get('payment_method') or {}
    if not pm.get('saved') or not pm.get('id'):
        return {'connected': False, 'reason': 'method_not_saved'}

    # Принадлежность платежа: metadata.user_id или локальная запись заказа.
    # Иначе чужой/поддельный payment_id привязал бы способ оплаты к другому юзеру.
    meta = p.get('metadata') or {}
    owner_ok = False
    if str(meta.get('user_id')) == str(user_id):
        owner_ok = True
    else:
        try:
            row = db.session.execute(text(
                "SELECT user_id FROM yookassa_payments WHERE payment_id = :pid LIMIT 1"
            ), {'pid': payment_id}).fetchone()
            if row and row[0] == user_id:
                owner_ok = True
        except Exception:  # noqa: BLE001
            pass
    if not owner_ok:
        logger.warning('[auto_renew] payment %s does not belong to user %s', payment_id, user_id)
        return {'connected': False, 'reason': 'payment_not_owned'}

    # Дата окончания подписки → дата следующего списания
    next_charge = _active_expires_at(user_id)

    # ВАЖНО: повторный вебхук/возврат по старому платежу НЕ включает обратно
    # выключенное автопродление — подтверждение оплаты не равно согласию
    # на будущие списания. enabled/fail_count текущей записи сохраняем.
    try:
        is_pg = db.engine.dialect.name == 'postgresql'
        if is_pg:
            db.session.execute(text(
                """
                INSERT INTO premium_auto_renewals
                    (user_id, plan, price_rub, payment_method_id, method_label,
                     enabled, next_charge_at, fail_count, created_at, updated_at)
                VALUES (:uid, :plan, :price, :pmid, :label, 1, :next, 0, :now, :now)
                ON CONFLICT (user_id) DO UPDATE SET
                    plan = :plan, price_rub = :price, payment_method_id = :pmid,
                    method_label = :label,
                    next_charge_at = COALESCE(:next, next_charge_at), updated_at = :now
                """
            ), {
                'uid': user_id, 'plan': plan, 'price': _plan_price(plan),
                'pmid': pm['id'], 'label': _method_label(pm),
                'next': next_charge, 'now': _now(),
            })
        else:
            # SQLite: SELECT-then-UPDATE (без ON CONFLICT DO UPDATE)
            cur = db.session.execute(text(
                "SELECT enabled, fail_count FROM premium_auto_renewals WHERE user_id = :uid"
            ), {'uid': user_id}).fetchone()
            if cur:
                db.session.execute(text(
                    "UPDATE premium_auto_renewals SET plan = :plan, price_rub = :price,"
                    " payment_method_id = :pmid, method_label = :label,"
                    " next_charge_at = COALESCE(:next, next_charge_at), updated_at = :now"
                    " WHERE user_id = :uid"
                ), {
                    'uid': user_id, 'plan': plan, 'price': _plan_price(plan),
                    'pmid': pm['id'], 'label': _method_label(pm),
                    'next': next_charge, 'now': _now(),
                })
            else:
                db.session.execute(text(
                    """
                    INSERT INTO premium_auto_renewals
                        (user_id, plan, price_rub, payment_method_id, method_label,
                         enabled, next_charge_at, fail_count, created_at, updated_at)
                    VALUES (:uid, :plan, :price, :pmid, :label, 1, :next, 0, :now, :now)
                    """
                ), {
                    'uid': user_id, 'plan': plan, 'price': _plan_price(plan),
                    'pmid': pm['id'], 'label': _method_label(pm),
                    'next': next_charge, 'now': _now(),
                })
        db.session.commit()
        logger.info('[auto_renew] saved method for user=%s plan=%s', user_id, plan)
        return {'connected': True, 'next_charge_at': next_charge}
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.error('[auto_renew] upsert failed: %r', e)
        return {'connected': False, 'reason': 'db_error'}


def _plan_price(plan: str):
    try:
        from routes.premium_pay import PLAN_INFO
        return float(PLAN_INFO[plan]['price_rub'])
    except Exception:  # noqa: BLE001
        return 800.0


def _method_label(pm: dict) -> str:
    t = pm.get('title') or ''
    if t:
        return str(t)[:60]
    return str(pm.get('type') or 'карта')[:60]


def _active_expires_at(user_id: int):
    """Дата окончания активной подписки (naive UTC) или None."""
    try:
        row = db.session.execute(text(
            "SELECT expires_at FROM subscriptions"
            " WHERE user_id = :uid AND status = 'active'"
            " ORDER BY expires_at DESC LIMIT 1"
        ), {'uid': user_id}).fetchone()
        if not row or not row[0]:
            return None
        v = row[0]
        return _to_dt(v)
    except Exception as e:  # noqa: BLE001
        logger.warning('[auto_renew] expires lookup failed: %r', e)
        return None


# ── Продление подписки (ровно один раз на период) ────────────────────────

def handle_succeeded_payment(order_id: str, payment_id: str = None,
                             user_id: int = None, plan: str = None) -> bool:
    """Применить успешный автосписок. True — это был наш заказ (обработано).

    Идемпотентно: повторный вебхук/джоба не продлевает дважды —
    атомарный перевод статуса попытки pending → applying.
    """
    ensure_tables()
    if not order_id:
        return False
    try:
        # Атомарный захват: только один воркер переводит pending → applying.
        # Зависшая попытка applying (воркер умер) — захватываем через 30 мин.
        res = db.session.execute(text(
            "UPDATE premium_renewal_attempts SET status = 'applying',"
            " payment_id = COALESCE(:pid, payment_id), updated_at = :now"
            " WHERE order_id = :oid"
            " AND (status = 'pending'"
            "      OR (status = 'applying' AND updated_at < :stale))"
        ), {'pid': payment_id, 'now': _now(), 'oid': order_id,
           'stale': _now() - timedelta(minutes=30)})
        claimed = (res.rowcount or 0) > 0
        row = db.session.execute(text(
            "SELECT id, renewal_id, period_start, period_end, status"
            " FROM premium_renewal_attempts WHERE order_id = :oid LIMIT 1"
        ), {'oid': order_id}).fetchone()
        if not row:
            db.session.commit()
            return False
        if not claimed:
            # Уже применено (или применяется другим воркером) — не трогаем
            db.session.commit()
            return True
        attempt_id, renewal_id, period_start, period_end, _ = row
        period_start = _to_dt(period_start)
        period_end = _to_dt(period_end)

        renewal = db.session.execute(text(
            "SELECT user_id, plan, price_rub FROM premium_auto_renewals"
            " WHERE id = :rid LIMIT 1"
        ), {'rid': renewal_id}).fetchone()
        if not renewal:
            _finish_attempt(attempt_id, 'failed', 'renewal_not_found')
            return True
        ar_user, ar_plan, ar_price = renewal

        # Продление: 30 дней от конца текущего периода (оплаченное не сгорает).
        # Подписка + следующий период + статус попытки фиксируются ОДНОЙ
        # транзакцией — упавший воркер не оставит «продлено, но не учтено».
        from services.subscription import get_subscription_service
        svc = get_subscription_service()
        svc.activate_premium(
            user_id=ar_user, plan=ar_plan,
            payment_id=f"yookassa:{payment_id or order_id}",
            is_beta=False, amount_rub=float(ar_price),
            starts_at=period_start, expires_at=period_end,
        )
        # Следующее списание — через 30 дней от нового конца периода.
        # enabled НЕ трогаем: повторная обработка платежа не включает
        # обратно выключенное автопродление.
        db.session.execute(text(
            "UPDATE premium_auto_renewals SET next_charge_at = :next,"
            " fail_count = 0, updated_at = :now WHERE id = :rid"
        ), {'next': period_end, 'now': _now(), 'rid': renewal_id})
        db.session.execute(text(
            "UPDATE premium_renewal_attempts SET status = 'succeeded', error = NULL,"
            " updated_at = :now WHERE id = :id"
        ), {'now': _now(), 'id': attempt_id})
        db.session.commit()  # явный commit: _commit() — no-op для SQLAlchemy
        logger.info('[auto_renew] renewed user=%s until %s', ar_user, period_end)
        return True
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.exception('[auto_renew] handle_succeeded_payment failed: %r', e)
        return True


def _finish_attempt(attempt_id: int, status: str, error: str) -> None:
    try:
        db.session.execute(text(
            "UPDATE premium_renewal_attempts SET status = :st, error = :err,"
            " updated_at = :now WHERE id = :id"
        ), {'st': status, 'err': error, 'now': _now(), 'id': attempt_id})
        db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()


# ── Ежечасная джоба ──────────────────────────────────────────────────────

def run_renewal_job() -> dict:
    """Списать автопродления, у которых срок подходит. Возвращает статистику.

    В демо-режиме (ЮKassa не настроена) ничего не делает.
    Аварийный стоп-кран: PREMIUM_AUTORENEW_ENABLED (по умолчанию '0' —
    реальные автосписания ВЫКЛЮЧЕНЫ, пока не включите осознанно).
    """
    if os.environ.get('PREMIUM_AUTORENEW_ENABLED', '0') != '1':
        return {'skipped': 'disabled_by_env'}
    ensure_tables()
    cfg = _yk_cfg()
    if not cfg.get('configured'):
        return {'skipped': 'not_configured'}

    stats = {'reconciled': 0, 'charged': 0, 'failed': 0, 'disabled': 0}

    # 1. Довести до конца зависшие попытки (статус платежа мог стать
    #    известен позже: вебхук не дошёл, джоба упала после запроса)
    try:
        pend = db.session.execute(text(
            "SELECT id, order_id, payment_id, renewal_id FROM premium_renewal_attempts"
            " WHERE status IN ('pending', 'unknown') AND payment_id IS NOT NULL"
            " AND created_at < :cutoff"
        ), {'cutoff': _now() - timedelta(minutes=10)}).fetchall()
        for a_id, a_order, a_pid, a_rid in pend:
            try:
                resp = requests.get(
                    f"{YOOKASSA_API_BASE}/payments/{a_pid}",
                    auth=(cfg['shop_id'], cfg['secret_key']), timeout=10,
                )
                if resp.status_code == 200:
                    remote = resp.json() or {}
                    if remote.get('status') == 'succeeded':
                        handle_succeeded_payment(a_order, a_pid)
                        stats['reconciled'] += 1
                    elif remote.get('status') == 'canceled':
                        _mark_failed(a_rid, a_order, 'canceled')
                        stats['failed'] += 1
            except Exception as e:  # noqa: BLE001
                logger.warning('[auto_renew] reconcile lookup failed: %r', e)
    except Exception as e:  # noqa: BLE001
        logger.warning('[auto_renew] reconcile query failed: %r', e)

    # 2. Найти подошедшие подписки и списать
    try:
        due = db.session.execute(text(
            "SELECT id, user_id, plan, price_rub, payment_method_id, next_charge_at"
            " FROM premium_auto_renewals"
            " WHERE enabled = 1 AND payment_method_id IS NOT NULL"
            " AND next_charge_at IS NOT NULL AND next_charge_at <= :horizon"
        ), {'horizon': _now() + RENEWAL_WINDOW}).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning('[auto_renew] due query failed: %r', e)
        return stats

    for rid, uid, plan, price, pm_id, next_at in due:
        try:
            _charge_renewal(rid, uid, plan, float(price), pm_id, stats)
        except Exception as e:  # noqa: BLE001
            logger.exception('[auto_renew] charge failed user=%s: %r', uid, e)
    return stats


def _charge_renewal(rid, uid, plan, price, pm_id, stats) -> None:
    cfg = _yk_cfg()

    # Период: от текущего конца подписки + 30 дней
    period_start = _active_expires_at(uid)
    if period_start is None:
        # Подписки нет — списывать не за что, выключаем
        db.session.execute(text(
            "UPDATE premium_auto_renewals SET enabled = 0, updated_at = :now WHERE id = :rid"
        ), {'now': _now(), 'rid': rid})
        db.session.commit()
        stats['disabled'] += 1
        return
    period_end = period_start + timedelta(days=30)

    # Уже есть попытка на этот период? (джоба перезапустилась)
    try:
        existing = db.session.execute(text(
            "SELECT id, status, order_id, created_at FROM premium_renewal_attempts"
            " WHERE renewal_id = :rid AND period_start = :ps LIMIT 1"
        ), {'rid': rid, 'ps': period_start}).fetchone()
        if existing:
            a_id, st, order_id, a_created = existing
            if st in ('succeeded', 'applying'):
                return
            if st == 'unknown':
                # Результат платежа не сверен — новых списаний за этот период
                # не делаем до ручной/авто-сверки (защита от двойного списания)
                return
            if st == 'failed':
                # Прежний платёж был отклонён: тот же Idempotence-Key вернул бы
                # тот же отклонённый платёж — нужен новый заказ.
                # АТОМАРНЫЙ ЗАХВАТ: только один воркер видит status='failed'.
                # created_at сбрасываем — считаем возраст НОВОГО ключа идемпотентности.
                new_order_id = uuid.uuid4().hex
                res = db.session.execute(text(
                    "UPDATE premium_renewal_attempts SET order_id = :oid,"
                    " payment_id = NULL, status = 'pending', error = NULL,"
                    " created_at = :now, updated_at = :now WHERE id = :id AND status = 'failed'"
                ), {'oid': new_order_id, 'now': _now(), 'id': a_id})
                if (res.rowcount or 0) == 0:
                    db.session.commit()
                    return  # другой воркер уже забрал
                order_id = new_order_id
                # Новый заказ — в ОДНОЙ транзакции с захватом (иначе сбой
                # вставки оставил бы попытку pending без записи платежа)
                db.session.execute(text(
                    "INSERT INTO yookassa_payments"
                    " (order_id, payment_id, user_id, item_code, amount_rub, status, created_at)"
                    " VALUES (:oid, NULL, :uid, :item, :amount, 'pending', :now)"
                ), {'oid': order_id, 'uid': uid, 'item': plan, 'amount': price, 'now': _now()})
                db.session.commit()
            else:
                # pending (в т.ч. после сетевого таймаута): тот же order_id —
                # Idempotence-Key ЮKassa вернёт исходный платёж, дубля не будет.
                # Но дольше 24ч ждать нельзя: срок жизни ключа у ЮKassa — сутки,
                # после этого повторный POST может создать ВТОРОЙ платёж.
                if a_created and _to_dt(a_created) < _now() - timedelta(hours=24):
                    db.session.execute(text(
                        "UPDATE premium_renewal_attempts SET status = 'unknown',"
                        " error = 'stale pending: idempotence window expired',"
                        " updated_at = :now WHERE id = :id"
                    ), {'now': _now(), 'id': a_id})
                    db.session.commit()
                    logger.warning('[auto_renew] attempt %s marked unknown (stale)', a_id)
                    return
        else:
            order_id = uuid.uuid4().hex
    except Exception as e:  # noqa: BLE001
        logger.warning('[auto_renew] attempt lookup failed: %r', e)
        db.session.rollback()
        return

    # Заказ в БД (fail-closed: без записи — платёж не создаём) — вебхук
    # найдёт item_code=plan и активацию по order_id.
    #  * новый период — вставляем и заказ, и попытку (одной транзакцией);
    #  * повтор после отказа — уже вставлено выше (одной транзакцией с захватом);
    #  * повтор pending — ничего не вставляем (тот же order_id).
    try:
        if not existing:
            db.session.execute(text(
                "INSERT INTO yookassa_payments"
                " (order_id, payment_id, user_id, item_code, amount_rub, status, created_at)"
                " VALUES (:oid, NULL, :uid, :item, :amount, 'pending', :now)"
            ), {'oid': order_id, 'uid': uid, 'item': plan, 'amount': price, 'now': _now()})
            db.session.execute(text(
                "INSERT INTO premium_renewal_attempts"
                " (renewal_id, period_start, period_end, order_id, status, created_at)"
                " VALUES (:rid, :ps, :pe, :oid, 'pending', :now)"
            ), {'rid': rid, 'ps': period_start, 'pe': period_end, 'oid': order_id, 'now': _now()})
            db.session.commit()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[auto_renew] attempt insert failed (charge NOT created): %r', e)
        return

    # Безакцептное списание сохранённым способом.
    # Перепроверяем enabled ПОСЛЕ выборки due: пользователь мог отключить
    # автопродление, пока джоба бежала (списывать без согласия нельзя).
    try:
        cur = db.session.execute(text(
            "SELECT enabled FROM premium_auto_renewals WHERE id = :rid"
        ), {'rid': rid}).fetchone()
        if not cur or not cur[0]:
            return
    except Exception as e:  # noqa: BLE001
        logger.warning('[auto_renew] enabled recheck failed: %r', e)
        return

    try:
        payload = {
            "amount": {"value": f"{price:.2f}", "currency": "RUB"},
            "capture": True,
            "payment_method_id": pm_id,
            "description": f"Автопродление Premium ({plan}) — FORMYLA",
            "metadata": {"order_id": order_id, "user_id": str(uid), "item": plan},
        }
        if cfg.get('send_receipt'):
            customer_email = None
            try:
                urow = db.session.execute(text(
                    "SELECT email FROM users WHERE id = :uid LIMIT 1"
                ), {'uid': uid}).fetchone()
                if urow and urow[0] and '@' in urow[0]:
                    customer_email = urow[0]
            except Exception:  # noqa: BLE001
                pass
            if customer_email:
                payload["receipt"] = {
                    "customer": {"email": customer_email},
                    "items": [{
                        "description": "Автопродление Premium (30 дней)",
                        "quantity": "1.00",
                        "amount": {"value": f"{price:.2f}", "currency": "RUB"},
                        "vat_code": 1,
                        "payment_mode": "full_payment",
                        "payment_subject": "service",
                    }],
                }
        resp = requests.post(
            f"{YOOKASSA_API_BASE}/payments",
            auth=(cfg['shop_id'], cfg['secret_key']),
            headers={"Idempotence-Key": order_id, "Content-Type": "application/json"},
            timeout=15,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        )
        yk = resp.json() if resp.content else {}
    except Exception as e:  # noqa: BLE001
        # Состояние неизвестно (таймаут): попытка остаётся pending,
        # реконсиляция проверит платёж по order_id/idempotence
        logger.warning('[auto_renew] charge network error (will reconcile): %r', e)
        stats['failed'] += 1
        return

    if resp.status_code not in (200, 201):
        err = yk.get('description') or yk.get('code') or f'HTTP {resp.status_code}'
        if resp.status_code >= 500 or resp.status_code == 429:
            # Результат НЕОПРЕДЕЛЁН: ЮKassa могла создать платёж, но ответ
            # не дошёл. Новую попытку не делаем (иначе возможен второй
            # платёж) — помечаем unknown, сверит реконсиляция по payment_id
            # или вручную.
            try:
                db.session.execute(text(
                    "UPDATE premium_renewal_attempts SET status = 'unknown',"
                    " error = :err, payment_id = COALESCE(:pid, payment_id),"
                    " updated_at = :now WHERE order_id = :oid AND status != 'succeeded'"
                ), {'err': str(err)[:500], 'pid': yk.get('id'), 'now': _now(), 'oid': order_id})
                db.session.commit()
            except Exception:  # noqa: BLE001
                db.session.rollback()
            stats['failed'] += 1
            return
        # Окончательный отказ (4xx): новая попытка по политике повторов
        _mark_failed(rid, order_id, str(err))
        stats['failed'] += 1
        return

    payment_id = yk.get('id')
    status = yk.get('status', 'pending')
    try:
        db.session.execute(text(
            "UPDATE premium_renewal_attempts SET payment_id = :pid, updated_at = :now"
            " WHERE order_id = :oid"
        ), {'pid': payment_id, 'now': _now(), 'oid': order_id})
        db.session.execute(text(
            "UPDATE yookassa_payments SET payment_id = :pid, status = :st"
            " WHERE order_id = :oid"
        ), {'pid': payment_id, 'st': status, 'oid': order_id})
        db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()

    if status == 'succeeded':
        handle_succeeded_payment(order_id, payment_id)
        stats['charged'] += 1
    elif status == 'canceled':
        _mark_failed(rid, order_id, 'canceled')
        stats['failed'] += 1
    else:
        # pending: списание в процессе — ответит вебхук или реконсиляция
        stats['charged'] += 1


def _mark_failed(rid: int, order_id: str, reason: str) -> None:
    """Неудачная попытка: пауза 24ч; после 3 подряд — выключить автопродление."""
    try:
        db.session.execute(text(
            "UPDATE premium_renewal_attempts SET status = 'failed', error = :err,"
            " updated_at = :now WHERE order_id = :oid AND status != 'succeeded'"
        ), {'err': reason[:500], 'now': _now(), 'oid': order_id})
        db.session.execute(text(
            """
            UPDATE premium_auto_renewals
            SET fail_count = fail_count + 1,
                next_charge_at = :next,
                enabled = CASE WHEN fail_count + 1 >= :maxf THEN 0 ELSE enabled END,
                updated_at = :now
            WHERE id = :rid
            """
        ), {'next': _now() + RETRY_PAUSE, 'maxf': MAX_FAILS, 'now': _now(), 'rid': rid})
        db.session.commit()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[auto_renew] mark_failed error: %r', e)
