"""Extracted legacy routes; URL, authentication and response contracts preserved."""

from datetime import datetime
from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required
from models import db

bp = Blueprint('billing', __name__)

PREMIUM_PLAN_CODES = ('premium', 'premium_monthly', 'premium_yearly')

@bp.route('/subscribe')
@login_required
def subscribe_page():
    """Страница выбора тарифа."""
    current_plan = current_user.current_plan or 'free'
    plan_expires_at = getattr(current_user, 'plan_expires_at', None)
    if plan_expires_at:
        plan_expires_at = str(plan_expires_at)[:10]
    return render_template('subscribe.html',
                           current_plan=current_plan,
                           plan_expires_at=plan_expires_at)


def _is_premium_plan(plan_value):
    """True, если строка тарифа считается Premium-доступом."""
    return (plan_value or '').strip().lower() in PREMIUM_PLAN_CODES


@bp.app_context_processor
def _inject_subscription_flags():
    """Глобальный флаг is_premium для всех шаблонов.

    Использовать в Jinja: {% if is_premium %}…{% endif %}.
    Также нормализует устаревшие значения 'premium_monthly' / 'premium_yearly'
    для текущего рендера (только в памяти — БД не трогаем здесь).
    """
    try:
        if current_user.is_authenticated:
            return {
                'is_premium': _is_premium_plan(current_user.current_plan),
            }
    except Exception:
        pass
    return {'is_premium': False}


@bp.route('/api/subscribe', methods=['POST'])
@login_required
def api_subscribe():
    """API активации Premium (демо — без оплаты).

    Тело: {plan: 'premium_monthly'|'premium_yearly'}.
    В БД сохраняем КАНОНИЧЕСКОЕ значение 'premium' — чтобы все шаблоны,
    проверяющие `current_plan == 'premium'`, отображали статус корректно
    после reload страницы.
    """
    data = request.get_json() or {}
    requested = data.get('plan', 'premium_monthly')

    if requested not in ('premium_monthly', 'premium_yearly'):
        return jsonify({'error': 'Неизвестный тариф'}), 400

    from datetime import timedelta
    if requested == 'premium_monthly':
        expires = datetime.utcnow() + timedelta(days=30)
    else:
        expires = datetime.utcnow() + timedelta(days=365)

    # КАНОНИЗАЦИЯ: всегда 'premium' в БД. Срок — в plan_expires_at.
    current_user.current_plan = 'premium'
    current_user.plan_expires_at = expires
    db.session.commit()

    return jsonify({
        'ok': True,
        'plan': 'premium',
        'plan_variant': requested,  # для аналитики/UI: monthly|yearly
        'expires_at': str(expires)[:10],
        'message': 'Premium активирован!'
    })


@bp.route('/api/cancel_subscription', methods=['POST'])
@login_required
def api_cancel_subscription():
    """API отмены подписки Premium."""
    if not current_user.current_plan or current_user.current_plan == 'free':
        return jsonify({'error': 'У вас нет активной подписки'}), 400

    current_user.current_plan = 'free'
    current_user.plan_expires_at = None
    db.session.commit()

    return jsonify({
        'ok': True,
        'message': 'Подписка отменена. Вы переведены на бесплатный тариф.'
    })


LEGACY_ENDPOINTS = ('subscribe_page', 'api_subscribe', 'api_cancel_subscription')