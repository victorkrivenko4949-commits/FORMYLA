# -*- coding: utf-8 -*-
"""
routes/premium_pay.py — PREMIUM_PAY_V1 (24.10.2026): оплата тарифов Premium.

Полный цикл покупки:
  * GET  /payments/premium/checkout?plan=premium_intense|premium_calm
         — страница оформления: что входит, цена, кнопка «Оплатить»
  * POST /payments/premium/create
         — создание платежа ЮKassa (item_code = тариф) и редирект на оплату
  * GET  /payments/premium/return?order_id=...
         — возврат с оплаты: проверка статуса + активация Premium

Вебхук — общий с значком (routes/yookassa_pay.py): по item_code
активирует premium_intense/premium_calm (30 дней полного доступа).

Подключение реальной оплаты (один раз, без правок кода):
  указать Shop ID и Секретный ключ ЮKassa в профиле (карточка ЮKassa)
  или в переменных окружения YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY.
  До этого работает демо-режим: «Оплатить» проводит платёж без списания
  (для теста полного цикла).

Доступен только пилотным аккаунтам (до запуска 3 ноября).
Отключить: PREMIUM_PAY_AUTOREG=0.
"""
import json
import logging
import os
import uuid
from datetime import datetime

import requests
from flask import (Blueprint, abort, current_app, jsonify, redirect,
                    render_template, request, url_for)
from flask_login import current_user, login_required
from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)

premium_pay_bp = Blueprint('premium_pay', __name__)

YOOKASSA_API_BASE = "https://api.yookassa.ru/v3"

PLAN_INFO = {
    'premium_intense': {
        'icon': '⚡',
        'short': 'Работяга',
        'title': 'Premium «Работяга»',
        'price_rub': 800,
        'tagline': 'Для готовых пахать',
        'features': [
            '6 занятий в неделю',
            '1 пробник в неделю — реальный вариант прошлых лет',
            '1 метод в неделю — 70% разбор + 3 задачи',
            '4 занятия — задачи дня',
            'ИИ-тьютор, куратор и генератор чертежей',
        ],
    },
    'premium_calm': {
        'icon': '🌿',
        'short': 'Спокойный',
        'title': 'Premium «Спокойный»',
        'price_rub': 500,
        'tagline': 'Без спешки',
        'features': [
            '3 занятия в неделю по 1.5 часа',
            '1 пробник в 2 недели',
            '1 метод в 2 недели',
            'Задачи дня и тесты — как у всех',
            'ИИ-тьютор, куратор и генератор чертежей',
        ],
    },
}


def _pilot_or_404():
    """Оплата Premium доступна только пилотным аккаунтам (до 3 ноября)."""
    from services.pilot import is_pilot_user
    if not (getattr(current_user, 'is_authenticated', False)
            and is_pilot_user(current_user.id)):
        abort(404)


def _yk_config() -> dict:
    """Конфиг ЮKassa (общий с значком-алмазом)."""
    try:
        from routes.yookassa_pay import get_yookassa_config
        return get_yookassa_config()
    except Exception as e:  # noqa: BLE001
        logger.warning('[premium_pay] yookassa config failed: %r', e)
        return {'configured': False, 'shop_id': '', 'secret_key': '',
                'send_receipt': False, 'is_test': False}


def activate_premium_for_payment(user_id: int, plan: str,
                                 payment_id=None, order_id=None) -> dict:
    """Активировать Premium после оплаты (30 дней, настоящий платный статус).

    Вызывается из вебхука ЮKassa и со страницы возврата. Идемпотентно
    на уровне подписки (activate_premium замещает предыдущую).
    """
    if plan not in PLAN_INFO:
        return {'ok': False, 'error': 'unknown plan'}
    price = PLAN_INFO[plan]['price_rub']
    try:
        from services.subscription import get_subscription_service
        svc = get_subscription_service()
        result = svc.activate_premium(
            user_id=user_id,
            plan=plan,
            payment_id=f"yookassa:{payment_id}" if payment_id else f"order:{order_id}",
            is_beta=False,
            amount_rub=price,
        )
        logger.info('[premium_pay] activated %s for user=%s (payment=%s)',
                    plan, user_id, payment_id)
        return {'ok': True, 'result': result}
    except Exception as e:  # noqa: BLE001
        logger.error('[premium_pay] activation failed user=%s: %r', user_id, e)
        return {'ok': False, 'error': str(e)}


# ── Страница оформления ────────────────────────────────────────────────────

@premium_pay_bp.route('/payments/premium/checkout', methods=['GET'])
@login_required
def checkout():
    _pilot_or_404()
    plan = request.args.get('plan', 'premium_intense')
    if plan not in PLAN_INFO:
        plan = 'premium_intense'
    info = PLAN_INFO[plan]
    cfg = _yk_config()
    return render_template('payments/premium_checkout.html',
                           plan=plan, info=info, cfg=cfg)


# ── Создание платежа ───────────────────────────────────────────────────────

@premium_pay_bp.route('/payments/premium/create', methods=['POST'])
@login_required
def create_payment():
    _pilot_or_404()
    data = request.get_json(silent=True) or {}
    plan = data.get('plan') or request.form.get('plan') or 'premium_intense'
    if plan not in PLAN_INFO:
        return jsonify({'error': 'Неизвестный тариф'}), 400

    info = PLAN_INFO[plan]
    cfg = _yk_config()

    order_id = uuid.uuid4().hex
    nick_label = current_user.nickname or f"id={current_user.id}"

    # ── Демо-режим (ЮKassa не настроена): платёж без списания ──────────
    if not cfg.get('configured'):
        try:
            db.session.execute(text(
                "INSERT INTO yookassa_payments "
                "(order_id, payment_id, user_id, item_code, amount_rub, status, confirmation_url, created_at) "
                "VALUES (:oid, :pid, :uid, :item, :amount, 'succeeded', NULL, :now)"
            ), {
                'oid': order_id, 'pid': f"demo_{order_id[:12]}", 'uid': current_user.id,
                'item': plan, 'amount': float(info['price_rub']), 'now': datetime.utcnow(),
            })
            db.session.commit()
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            logger.warning('[premium_pay] demo insert failed: %r', e)
        return jsonify({'ok': True, 'demo': True, 'order_id': order_id,
                        'redirect': f"/payments/premium/return?order_id={order_id}&demo=1"})

    # ── Реальный платёж ЮKassa ──────────────────────────────────────────
    return_url = url_for('premium_pay.payment_return', order_id=order_id, _external=True)
    payload = {
        "amount": {"value": f"{info['price_rub']}.00", "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": return_url},
        "description": f"{info['title']} на FORMYLA (30 дней) — @{nick_label}",
        "metadata": {
            "order_id": order_id,
            "user_id": str(current_user.id),
            "item": plan,
        },
    }
    if cfg.get('send_receipt'):
        customer_email = current_user.email if (current_user.email and '@' in current_user.email) else ''
        if customer_email:
            payload["receipt"] = {
                "customer": {"email": customer_email},
                "items": [{
                    "description": f"{info['title']} (30 дней)",
                    "quantity": "1.00",
                    "amount": {"value": f"{info['price_rub']}.00", "currency": "RUB"},
                    "vat_code": 1,
                    "payment_mode": "full_payment",
                    "payment_subject": "service",
                }],
            }

    try:
        resp = requests.post(
            f"{YOOKASSA_API_BASE}/payments",
            auth=(cfg['shop_id'], cfg['secret_key']),
            headers={"Idempotence-Key": order_id, "Content-Type": "application/json"},
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            timeout=15,
        )
        yk = resp.json() if resp.content else {}
    except Exception as e:  # noqa: BLE001
        logger.exception('[premium_pay] yookassa request failed: %r', e)
        return jsonify({'error': 'Ошибка соединения с ЮKassa'}), 502

    if resp.status_code not in (200, 201):
        err = yk.get('description') or yk.get('code') or f'HTTP {resp.status_code}'
        logger.error('[premium_pay] yookassa rejected: %s', err)
        return jsonify({'error': f'ЮKassa отклонила платёж: {err}'}), 502

    confirmation_url = (yk.get('confirmation') or {}).get('confirmation_url')
    payment_id = yk.get('id')
    status = yk.get('status', 'pending')

    try:
        db.session.execute(text(
            "INSERT INTO yookassa_payments "
            "(order_id, payment_id, user_id, item_code, amount_rub, status, confirmation_url, created_at) "
            "VALUES (:oid, :pid, :uid, :item, :amount, :st, :curl, :now)"
        ), {
            'oid': order_id, 'pid': payment_id, 'uid': current_user.id, 'item': plan,
            'amount': float(info['price_rub']), 'st': status, 'curl': confirmation_url,
            'now': datetime.utcnow(),
        })
        db.session.commit()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[premium_pay] payment row insert failed: %r', e)

    if not confirmation_url:
        return jsonify({'error': 'ЮKassa не вернула ссылку на оплату'}), 502
    return jsonify({'ok': True, 'redirect': confirmation_url})


# ── Возврат с оплаты ────────────────────────────────────────────────────────

@premium_pay_bp.route('/payments/premium/return', methods=['GET'])
@login_required
def payment_return():
    _pilot_or_404()
    order_id = request.args.get('order_id') or ''
    demo = request.args.get('demo') == '1'
    if not order_id:
        return redirect('/subscribe')

    # Платёж в базе
    row = None
    try:
        row = db.session.execute(text(
            "SELECT user_id, item_code, status, payment_id FROM yookassa_payments "
            "WHERE order_id = :oid LIMIT 1"
        ), {'oid': order_id}).fetchone()
    except Exception as e:  # noqa: BLE001
        logger.warning('[premium_pay] return lookup failed: %r', e)

    if not row:
        return render_template('payments/premium_result.html',
                               status='not_found', info=None, plan=None), 404

    p_user_id, item_code, p_status, payment_id = row[0], row[1], row[2], row[3]
    if p_user_id != current_user.id:
        abort(403)

    plan = item_code if item_code in PLAN_INFO else None
    info = PLAN_INFO.get(plan) if plan else None

    # Демо-режим: активируем сразу
    if demo and p_status == 'succeeded':
        activate_premium_for_payment(current_user.id, plan, payment_id, order_id)
        return render_template('payments/premium_result.html',
                               status='succeeded', info=info, plan=plan, demo=True)

    # Реальный платёж: перепроверяем статус в API ЮKassa
    cfg = _yk_config()
    if cfg.get('configured') and payment_id and not str(payment_id).startswith('demo_'):
        try:
            resp = requests.get(
                f"{YOOKASSA_API_BASE}/payments/{payment_id}",
                auth=(cfg['shop_id'], cfg['secret_key']),
                timeout=10,
            )
            if resp.status_code == 200:
                remote = resp.json() or {}
                p_status = remote.get('status') or p_status
        except Exception as e:  # noqa: BLE001
            logger.warning('[premium_pay] return verify failed: %r', e)

    if p_status == 'succeeded':
        # Активация (вебхук мог уже сделать это — activate_premium идемпотентен
        # на уровне «замещает предыдущую»)
        activate_premium_for_payment(current_user.id, plan, payment_id, order_id)
        return render_template('payments/premium_result.html',
                               status='succeeded', info=info, plan=plan)

    if p_status == 'canceled':
        return render_template('payments/premium_result.html',
                               status='canceled', info=info, plan=plan)

    return render_template('payments/premium_result.html',
                           status='pending', info=info, plan=plan)


def install_premium_pay(app, register=None) -> None:
    """Регистрация blueprint'а (вызывается из routes/__init__.py)."""
    if app.extensions.get('premium_pay_installed'):
        return
    app.extensions['premium_pay_installed'] = True
    if register is None:
        app.register_blueprint(premium_pay_bp)
    else:
        register(app, premium_pay_bp)
