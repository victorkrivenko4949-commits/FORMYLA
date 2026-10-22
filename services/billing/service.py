# -*- coding: utf-8 -*-
"""Бизнес-логика оплаты (BILLING_V1).

Инварианты:
  * получателя, цену, период и признак Основателя определяет только сервер;
  * доступ выдаётся только по GET /payments/{id} в API ЮKassa (источник истины);
  * перевод в paid + выдача доступа — одна транзакция под SELECT ... FOR UPDATE;
  * повтор ничего не меняет; расхождение → лог + без доступа; временная ошибка → исключение
    TemporaryFailure (webhook отвечает 5xx, ЮKassa повторит).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from models import db
from models_billing import AnalyticsEvent, Order, Purchase
from services.billing import yookassa_client as yk
from services.billing.catalog import (CURRENCY, PRICE_VERSION, amount_for, get_product,
                                      is_product_enabled)
from services.billing.periods import PeriodRuleUnclear, compute_period, to_naive_utc

logger = logging.getLogger(__name__)

RETRY_WINDOW = timedelta(minutes=15)


class BillingError(Exception):
    status = 400

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.message = message
        if status:
            self.status = status


class BillingDisabled(BillingError):
    status = 403


class ProductUnavailable(BillingError):
    status = 400


class PeriodUnclear(BillingError):
    status = 409


class TemporaryFailure(BillingError):
    status = 503


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None or v == '':
        return default
    return v.strip().lower() in ('1', 'true', 'yes', 'on')


def create_enabled() -> bool:
    return _env_bool('BILLING_CREATE_ENABLED', False)


# ─────────────────────────── создание заказа ───────────────────────────

def create_order(user, plan_code: str, return_url_for: Callable[[str], str]) -> Order:
    """Локальный заказ → платёж ЮKassa (Idempotence-Key = orders.idempotence_key).

    Повтор после тайм-аута переиспользует заказ в статусе created (тот же ключ).
    user_id / child_user_id / сумма из браузера сюда не попадают по построению.
    """
    if not create_enabled():
        raise BillingDisabled('Оплата временно недоступна.')
    product = get_product(plan_code)
    if product is None or not is_product_enabled(product):
        raise ProductUnavailable('Этот тариф сейчас недоступен.')

    now = datetime.utcnow()
    order = (Order.query
             .filter_by(payer_user_id=user.id, plan_code=product.code, status='created')
             .filter(Order.yookassa_payment_id.is_(None), Order.created_at > now - RETRY_WINDOW)
             .order_by(Order.created_at.desc()).first())
    if order is None:
        amount, founder_applied = amount_for(product, user)
        try:
            starts, ends = compute_period(product, user)
        except PeriodRuleUnclear as exc:
            raise PeriodUnclear(str(exc))
        order = Order(
            payer_user_id=user.id,
            beneficiary_user_id=user.id,      # family/teacher в первом релизе не продаются
            plan_code=product.code,
            amount=amount, currency=CURRENCY, price_version=PRICE_VERSION,
            founder_applied=founder_applied, status='created',
            access_starts_at=to_naive_utc(starts) if starts else None,
            access_ends_at=to_naive_utc(ends) if ends else None,
        )
        db.session.add(order)
        db.session.commit()

    try:
        resp = yk.create_payment(
            amount_kop=order.amount, currency=order.currency,
            description=f'FORMYLA: {product.title}',
            return_url=return_url_for(order.id),
            idempotence_key=order.idempotence_key, order_id=order.id)
    except yk.YooKassaTemporaryError:
        # заказ остаётся created, следующий вызов пойдёт с тем же ключом
        raise TemporaryFailure('Платёжный сервис не ответил. Повторите через минуту.')
    except yk.YooKassaError as exc:
        logger.error('billing.create_order: order=%s rejected: %s', order.id, exc)
        order.status = 'failed'
        order.note = 'create_rejected'
        db.session.commit()
        raise BillingError('Платёжный сервис отклонил запрос.', 502)

    # webhook мог успеть раньше — не затираем paid
    locked = db.session.execute(select(Order).where(Order.id == order.id).with_for_update()).scalar_one()
    if locked.yookassa_payment_id is None:
        locked.yookassa_payment_id = resp['id']
    locked.confirmation_url = resp['confirmation']['confirmation_url']
    if locked.status == 'created':
        locked.status = 'pending'
    if resp.get('test') is not None:
        locked.is_test = bool(resp.get('test'))
    db.session.commit()
    logger.info('billing: order=%s payment=%s status=%s', locked.id, locked.yookassa_payment_id, locked.status)
    return locked


# ─────────────────────────── подтверждение ───────────────────────────

def _validate(order: Order, payment: Dict) -> List[str]:
    problems: List[str] = []
    pid = payment.get('id')
    if order.yookassa_payment_id and pid != order.yookassa_payment_id:
        problems.append('payment_id_mismatch')
    meta_order = str((payment.get('metadata') or {}).get('order_id') or '')
    if meta_order != order.id:
        problems.append('foreign_order')
    amt = payment.get('amount') or {}
    try:
        if yk.value_to_kop(amt.get('value')) != int(order.amount):
            problems.append('amount_mismatch')
    except Exception:
        problems.append('amount_unreadable')
    if (amt.get('currency') or '') != order.currency:
        problems.append('currency_mismatch')
    if payment.get('test') and os.environ.get('YOOKASSA_MODE', 'live') == 'live':
        problems.append('test_payment_in_live')
    if payment.get('status') == 'succeeded' and payment.get('paid') is False:
        problems.append('not_paid_flag')
    return problems


def _grant_access(order: Order) -> None:
    """Выдача доступа внутри текущей транзакции (без commit)."""
    product = get_product(order.plan_code)
    if product is None:
        raise BillingError(f'unknown plan {order.plan_code}', 500)
    if product.kind == 'access':
        from services.subscription import get_subscription_service
        get_subscription_service().activate_premium(
            order.beneficiary_user_id, plan=product.plan,
            payment_id=order.yookassa_payment_id, is_beta=False,
            amount_rub=order.amount // 100,
            starts_at=order.access_starts_at, expires_at=order.access_ends_at)
    else:
        db.session.add(Purchase(order_id=order.id, user_id=order.beneficiary_user_id,
                                product_code=product.code))


def confirm_payment(order_id: str, payment: Dict) -> str:
    """Применить проверенный объект платежа к заказу.

    Возвращает: paid | already_paid | mismatch | failed | ignored.
    Ошибки БД пробрасываются наверх (webhook → 5xx).
    """
    order = db.session.execute(select(Order).where(Order.id == order_id).with_for_update()).scalar_one_or_none()
    if order is None:
        db.session.rollback()
        return 'ignored'
    if order.status == 'paid':
        db.session.rollback()
        return 'already_paid'

    status = payment.get('status')
    if status == 'canceled':
        order.status = 'failed'
        order.note = 'canceled'
        db.session.commit()
        return 'failed'
    if status != 'succeeded':
        db.session.rollback()
        return 'ignored'

    problems = _validate(order, payment)
    if problems:
        order.note = ';'.join(problems)[:200]
        db.session.commit()
        logger.warning('billing.webhook: order=%s payment=%s MISMATCH %s (no access)',
                       order.id, payment.get('id'), problems)
        return 'mismatch'

    try:
        if order.yookassa_payment_id is None:
            order.yookassa_payment_id = payment.get('id')
        order.status = 'paid'
        order.paid_at = datetime.utcnow()
        order.is_test = bool(payment.get('test'))
        _grant_access(order)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    logger.info('billing: order=%s payment=%s PAID', order.id, order.yookassa_payment_id)

    # после commit: серверное событие (идемпотентно по order_id) и воронка
    record_payment_event(order)
    try:
        from services.funnel import payment_success
        payment_success(order.beneficiary_user_id, order.plan_code, order.amount / 100,
                        payment_id=order.yookassa_payment_id, props={'order_id': order.id})
    except Exception as exc:
        logger.debug('billing: funnel.payment_success skipped: %r', exc)
    return 'paid'


def record_payment_event(order: Order) -> bool:
    try:
        db.session.add(AnalyticsEvent(event='payment_success', order_id=order.id,
                                      user_id=order.beneficiary_user_id, plan_code=order.plan_code,
                                      amount=order.amount, is_test=order.is_test))
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False
    except Exception as exc:
        db.session.rollback()
        logger.warning('billing: analytics_events insert failed order=%s: %r', order.id, exc)
        return False


def mark_client_goal_sent(order_id: str) -> bool:
    """Атомарно помечает событие как отданное в браузер. True — отдать цель ровно сейчас."""
    try:
        res = db.session.execute(text(
            "UPDATE analytics_events SET client_sent_at = :now "
            "WHERE order_id = :o AND event = 'payment_success' AND client_sent_at IS NULL"
        ), {'now': datetime.utcnow(), 'o': order_id})
        db.session.commit()
        return bool(res.rowcount)
    except Exception as exc:
        db.session.rollback()
        logger.warning('billing: mark_client_goal_sent failed order=%s: %r', order_id, exc)
        return False


def process_webhook(body: Dict) -> str:
    """Из тела уведомления берём только object.id и metadata.order_id; остальное — из API."""
    obj = body.get('object') or {}
    pid = obj.get('id')
    order_id = str((obj.get('metadata') or {}).get('order_id') or '') or None
    order = db.session.get(Order, order_id) if order_id else None
    if order is None and pid:
        order = Order.query.filter_by(yookassa_payment_id=pid).first()
    if order is None:
        logger.warning('billing.webhook: unknown order (order_id=%s payment=%s)', order_id, pid)
        return 'ignored'
    if order.status == 'paid':
        return 'already_paid'
    if not pid:
        return 'ignored'
    try:
        payment = yk.get_payment(pid)
    except yk.YooKassaTemporaryError as exc:
        raise TemporaryFailure(str(exc))
    except yk.YooKassaError as exc:
        logger.error('billing.webhook: get_payment failed order=%s: %s', order.id, exc)
        return 'ignored'
    return confirm_payment(order.id, payment)


# ─────────────────────────── сверка ───────────────────────────

def reconcile(max_age_minutes: int = 2, expire_after_hours: int = 24) -> Dict[str, int]:
    """flask billing-reconcile: зависшие pending → сверка с API; старые created → expired."""
    now = datetime.utcnow()
    counters = {'checked': 0, 'paid': 0, 'failed': 0, 'mismatch': 0, 'expired': 0, 'temporary': 0, 'unchanged': 0}
    stale = (Order.query.filter(Order.status.in_(('created', 'pending')),
                                Order.created_at < now - timedelta(minutes=max_age_minutes)).all())
    for o in stale:
        if o.yookassa_payment_id is None:
            if o.created_at < now - timedelta(hours=expire_after_hours):
                o.status = 'expired'
                db.session.commit()
                counters['expired'] += 1
            continue
        counters['checked'] += 1
        try:
            res = confirm_payment(o.id, yk.get_payment(o.yookassa_payment_id))
        except yk.YooKassaTemporaryError:
            counters['temporary'] += 1
            continue
        except yk.YooKassaError:
            counters['unchanged'] += 1
            continue
        counters[res if res in counters else 'unchanged'] += 1
    # событие могло не записаться после commit — дописываем
    missing = db.session.execute(text(
        "SELECT o.id FROM orders o LEFT JOIN analytics_events e ON e.order_id = o.id "
        "WHERE o.status = 'paid' AND e.id IS NULL")).fetchall()
    for (oid,) in missing:
        record_payment_event(db.session.get(Order, oid))
    return counters
