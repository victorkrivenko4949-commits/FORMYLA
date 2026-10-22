# -*- coding: utf-8 -*-
"""BILLING_V1 — blueprint /billing (ЮKassa). Регистрируется из routes/__init__.py,
app.py не трогаем. Отключить: BILLING_AUTOREG=0. Остановить новые платежи:
BILLING_CREATE_ENABLED=0 (webhook продолжает работать)."""
from __future__ import annotations

import logging
import os

import click
from flask import Blueprint, abort, jsonify, redirect, render_template, request
from flask_login import current_user, login_required
from sqlalchemy.exc import DBAPIError, OperationalError

from models import db
from services.billing import service as billing
from services.billing.webhook_ip import ip_allowed
from services.security import validate_csrf

logger = logging.getLogger(__name__)

# template_folder нужен тестам: приложение из tests/conftest.py создаётся как Flask(__name__) в tests/
_TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates')
billing_bp = Blueprint('billing', __name__, url_prefix='/billing', template_folder=_TEMPLATES)
ALLOWED_EVENTS = ('payment.succeeded', 'payment.canceled', 'payment.waiting_for_capture')


def _public_base() -> str:
    base = os.environ.get('PUBLIC_BASE_URL', '').strip().rstrip('/')
    return base or request.url_root.rstrip('/')


def _return_url_for(order_id: str) -> str:
    # формируется сервером; никаких return_url из браузера
    return f'{_public_base()}/billing/success?order={order_id}'


def _wants_json() -> bool:
    return request.is_json or 'application/json' in (request.headers.get('Accept') or '')


def _csrf_ok() -> bool:
    token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
    if token is None and request.is_json:
        token = (request.get_json(silent=True) or {}).get('csrf_token')
    return validate_csrf(token or '')


@billing_bp.route('/create', methods=['POST'])
@login_required
def create():
    if not _csrf_ok():
        return jsonify(error='csrf'), 403
    data = request.get_json(silent=True) if request.is_json else request.form
    plan_code = (data or {}).get('plan_code') or ''
    try:
        order = billing.create_order(current_user, plan_code, _return_url_for)
    except billing.BillingError as exc:
        if _wants_json():
            return jsonify(error=type(exc).__name__, message=exc.message), exc.status
        return render_template('billing/success.html', order=None, error=exc.message,
                               send_goal=False, poll=False), exc.status
    if _wants_json():
        return jsonify(order_id=order.id, confirmation_url=order.confirmation_url)
    return redirect(order.confirmation_url, code=303)


@billing_bp.route('/webhook', methods=['POST'])
def webhook():
    if not ip_allowed(request.remote_addr):
        logger.warning('billing.webhook: forbidden ip=%s', request.remote_addr)
        return '', 403
    body = request.get_json(silent=True) or {}
    if body.get('type') != 'notification' or body.get('event') not in ALLOWED_EVENTS:
        return jsonify(result='ignored'), 200
    try:
        result = billing.process_webhook(body)
    except billing.TemporaryFailure:
        return '', 503
    except (OperationalError, DBAPIError) as exc:
        db.session.rollback()
        logger.error('billing.webhook: db error: %s', type(exc).__name__)
        return '', 503
    return jsonify(result=result), 200


def _own_order_or_404(order_id: str):
    from models_billing import Order
    order = db.session.get(Order, order_id) if order_id else None
    if order is None or order.payer_user_id != current_user.id:
        abort(404)
    return order


@billing_bp.route('/success')
@login_required
def success():
    order = _own_order_or_404(request.args.get('order', ''))
    send_goal = order.status == 'paid' and billing.mark_client_goal_sent(order.id)
    return render_template('billing/success.html', order=order, error=None, send_goal=send_goal,
                           poll=order.status in ('created', 'pending'),
                           metrika_id=os.environ.get('YANDEX_METRIKA_ID', ''))


@billing_bp.route('/status/<order_id>')
@login_required
def status(order_id: str):
    order = _own_order_or_404(order_id)
    return jsonify(status=order.status, paid=order.status == 'paid')


@click.command('billing-reconcile')
def billing_reconcile_cmd():
    """Сверка зависших заказов с API ЮKassa."""
    counters = billing.reconcile()
    click.echo(' '.join(f'{k}={v}' for k, v in counters.items()))


def install_billing(app, register=None) -> None:
    if app.extensions.get('billing_installed'):
        return
    app.extensions['billing_installed'] = True
    import models_billing  # noqa: F401 — таблицы попадают в metadata для auto_migrate
    if 'billing' not in app.blueprints:
        (register or type(app).register_blueprint)(app, billing_bp)
    app.cli.add_command(billing_reconcile_cmd)
    logger.info('BILLING_V1 registered (/billing/create, /billing/webhook, /billing/success, /billing/status)')
