# -*- coding: utf-8 -*-
"""BILLING_V1 (18.10.2026) — blueprint `billing`: витрина /subscribe, создание платежа,
страница успеха, webhook ЮKassa, отмена подписки.

  GET  /subscribe?from=…      витрина тарифов (цены Основателя — по services.billing_plans.is_founder)
  POST /billing/create        {plan} → платёж ЮKassa → redirect на confirmation_url
  GET  /billing/success       возврат после оплаты; статус берём из таблицы payments
  POST /billing/webhook       уведомления ЮKassa (payment.succeeded / payment.canceled)
  POST /billing/cancel        cancel_subscription(current_user)
  GET  /billing/status.json   текущий план пользователя (для шапки/экрана лимита)

Откат: BILLING_ENABLED=0. Без YOOKASSA_* ключей витрина работает, кнопки оплаты
заменяются на «скоро». Не правит app.py — подключение через routes/__init__.py.
"""
from __future__ import annotations

import logging
import os

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

logger = logging.getLogger(__name__)

billing_bp = Blueprint('billing', __name__)

ENABLED = os.environ.get('BILLING_ENABLED', '1') != '0'


def _return_url() -> str:
    return os.environ.get('YOOKASSA_RETURN_URL') or (request.url_root.rstrip('/') + '/billing/success')


def _current_plan(uid: int) -> dict:
    try:
        from services.subscription import get_subscription_service
        return get_subscription_service().get_user_plan(uid)
    except Exception as e:  # noqa: BLE001
        logger.warning('billing: get_user_plan failed: %r', e)
        return {'plan': 'free', 'display_name': 'Бесплатный', 'expires_at': None, 'is_premium': False}


def _track(name: str, props: dict | None = None) -> None:
    try:
        from services.funnel import track
        track(name, props or {})
    except Exception:
        pass


# ──────────────────────────── витрина ────────────────────────────
@billing_bp.route('/subscribe')
@login_required
def subscribe():
    from services.billing_plans import FROM_TITLES, catalog, is_founder
    from services import payments_yookassa as yk
    frm = (request.args.get('from') or '')[:80]
    founder = is_founder(current_user)
    plan = _current_plan(current_user.id)
    _track('subscribe_view', {'from': frm or None, 'founder': founder, 'plan': plan.get('plan')})
    return render_template('billing/subscribe.html',
                           items=catalog(founder), founder=founder, plan=plan,
                           heading=FROM_TITLES.get(frm, 'Подписка FORMYLA'), frm=frm,
                           payments_ready=ENABLED and yk.configured(),
                           founder_until='31.01.2027')


@billing_bp.route('/billing/create', methods=['POST'])
@login_required
def create():
    if not ENABLED:
        abort(404)
    from services.billing_plans import PLANS, is_founder, price_for
    from services import payments_yookassa as yk
    data = request.get_json(silent=True) or request.form
    code = (data.get('plan') or '').strip()
    if code not in PLANS:
        return jsonify(ok=False, error='unknown_plan'), 400
    if not yk.configured():
        return jsonify(ok=False, error='payments_not_configured'), 503
    founder = is_founder(current_user)
    amount = price_for(code, founder)
    p = PLANS[code]
    desc = f"FORMYLA · {p['title']} ({p['period']})"
    extra = {}
    if data.get('child_user_id'):
        extra['child_user_id'] = data.get('child_user_id')
    if founder:
        extra['founder'] = 1
    try:
        payment = yk.create_payment(current_user.id, code, amount, desc, _return_url(), extra)
    except Exception as e:  # noqa: BLE001
        logger.exception('billing.create failed: %r', e)
        return jsonify(ok=False, error='payment_create_failed'), 502
    url = ((payment.get('confirmation') or {}).get('confirmation_url'))
    if not url:
        return jsonify(ok=False, error='no_confirmation_url'), 502
    _track('payment_started', {'plan': code, 'amount': amount, 'founder': founder})
    if request.is_json:
        return jsonify(ok=True, payment_id=payment.get('id'), confirmation_url=url)
    return redirect(url)


@billing_bp.route('/billing/success')
@login_required
def success():
    from services import payments_yookassa as yk
    plan = _current_plan(current_user.id)
    last = None
    try:
        from sqlalchemy import text
        from models import db
        yk.ensure_tables()
        last = db.session.execute(text("""SELECT payment_id, plan, amount, status FROM payments
                                          WHERE user_id = :u ORDER BY id DESC LIMIT 1"""), {'u': current_user.id}).first()
    except Exception:
        pass
    return render_template('billing/success.html', plan=plan, last=last)


@billing_bp.route('/billing/cancel', methods=['POST'])
@login_required
def cancel():
    try:
        from services.subscription import get_subscription_service
        from models import db
        ok = get_subscription_service().cancel_subscription(current_user.id)
        db.session.commit()
    except Exception as e:  # noqa: BLE001
        logger.exception('billing.cancel failed: %r', e)
        ok = False
    _track('subscription_cancel', {'ok': ok})
    if request.is_json:
        return jsonify(ok=bool(ok))
    return redirect(url_for('billing.subscribe', **{'from': 'profile'}))


@billing_bp.route('/billing/status.json')
@login_required
def status_json():
    from services.billing_plans import is_founder
    plan = _current_plan(current_user.id)
    return jsonify(plan=plan.get('plan'), display_name=plan.get('display_name'),
                   expires_at=plan.get('expires_at'), is_premium=bool(plan.get('is_premium')),
                   is_founder=is_founder(current_user))


# ──────────────────────────── webhook ────────────────────────────
@billing_bp.route('/billing/webhook', methods=['POST'])
def webhook():
    """ЮKassa ждёт 200; при 4xx/5xx повторяет. Чужой IP — 403, остальное — 200 с reason."""
    from services import payments_yookassa as yk
    payload = request.get_json(silent=True) or {}
    remote = request.headers.get('X-Forwarded-For', request.remote_addr)
    ok, reason = yk.handle_notification(payload, remote)
    if reason == 'forbidden_ip':
        return jsonify(ok=False, reason=reason), 403
    if reason in ('verify_failed', 'fulfil_failed'):
        return jsonify(ok=False, reason=reason), 500   # пусть ЮKassa повторит
    return jsonify(ok=ok, reason=reason), 200


# ──────────────────────────── install ────────────────────────────
def install(app) -> None:
    if not ENABLED or app.extensions.get('billing_installed'):
        return
    app.extensions['billing_installed'] = True
    if 'billing' not in app.blueprints:
        app.register_blueprint(billing_bp)
    try:
        from services import payments_yookassa as yk
        with app.app_context():
            yk.ensure_tables()
    except Exception as e:  # noqa: BLE001
        logger.warning('billing: ensure_tables failed: %r', e)
    logger.info('BILLING_V1 registered (/subscribe, /billing/*)')
