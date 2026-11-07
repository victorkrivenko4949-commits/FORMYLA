# -*- coding: utf-8 -*-
"""
routes/seat_pay.py — SEAT_SUBSCRIPTION_V1 (07.11.2026)

Подписки на МЕСТА — единая линейка для учителя и родителя
(UNIFIED_SEATS_V1, 08.11.2026):
  Одно место 800 ₽ / Старт до 5 мест 1500 ₽ / Группа до 15 мест 3000 ₽ / Кружок до 50 мест 5000 ₽

Реальная оплата через ЮKassa (разовая, 30 дней, без автопродления —
контур тот же, что у Premium: yookassa_payments + вебхук + страница возврата).
После оплаты активируется запись в seat_subscriptions — по ней:
  • в кабинетах возвращается форма добавления учеников/детей;
  • маршруты добавления проверяют подписку и лимит мест.

Маршруты:
  GET  /payments/seats/checkout?plan=seat_teacher_group — оформление
  POST /payments/seats/create                            — платёж ЮKassa
  GET  /payments/seats/return?order_id=...               — возврат + активация
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta

import requests
from flask import (Blueprint, abort, current_app, jsonify, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required
from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)

seat_pay_bp = Blueprint('seat_pay', __name__)

YOOKASSA_API_BASE = "https://api.yookassa.ru/v3"

SEAT_PLANS = {
    # UNIFIED_SEATS_V1 (08.11.2026, владелец): единая линейка для учителя
    # и родителя — без деления по роли. Роль видна только в кабинете
    # («Мои ученики» — учитель, «Мои гении» — родитель).
    'seat_one': {
        'icon': '🧒', 'title': 'Одно место',
        'seats': 1, 'price_rub': 800, 'tagline': '1 место',
        'features': [
            'Одно место для ученика или ребёнка',
            'Статистика: задачи дня, серия, уровни',
            'Красная зона и рекомендации',
        ],
    },
    'seat_start': {
        'icon': '🌱', 'title': 'Старт',
        'seats': 5, 'price_rub': 1500, 'tagline': 'до 5 мест',
        'features': [
            'До 5 мест для учеников или детей',
            'Статистика каждого: задачи дня, серия, уровни',
            'Красная зона и рекомендации по режиму',
            'Приглашения по коду и по никнейму',
        ],
    },
    'seat_group': {
        'icon': '👥', 'title': 'Группа',
        'seats': 15, 'price_rub': 3000, 'tagline': 'до 15 мест',
        'features': [
            'До 15 мест для учеников или детей',
            'Статистика каждого: задачи дня, серия, уровни',
            'Красная зона и рекомендации по режиму',
            'Приглашения по коду и по никнейму',
        ],
    },
    'seat_kruzhok': {
        'icon': '🏫', 'title': 'Кружок',
        'seats': 50, 'price_rub': 5000, 'tagline': 'до 50 мест',
        'features': [
            'До 50 мест для учеников или детей',
            'Статистика каждого: задачи дня, серия, уровни',
            'Красная зона и рекомендации по режиму',
            'Приглашения по коду и по никнейму',
        ],
    },
}

# Старые коды тарифов (до объединения линейки) — для отображения уже
# активных подписок и активации незавершённых заказов.
SEAT_ALIASES = {
    'seat_teacher_start': 'seat_start',
    'seat_teacher_group': 'seat_group',
    'seat_teacher_kruzhok': 'seat_kruzhok',
    'seat_parent_one': 'seat_one',
    'seat_parent_family': 'seat_start',
    'seat_parent_big': 'seat_start',
}


def resolve_seat_plan(plan: str) -> str:
    """Код тарифа (в т.ч. старый) → код в SEAT_PLANS."""
    return SEAT_ALIASES.get(plan, plan)


# ── Таблицы ─────────────────────────────────────────────────────────────

def _ensure_tables() -> None:
    """seat_subscriptions (каждая DDL в своей транзакции — PostgreSQL-safe)."""
    is_pg = db.engine.name == 'postgresql'
    id_col = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    stmts = [
        (f"CREATE TABLE IF NOT EXISTS seat_subscriptions ("
         f" id {id_col},"
         f" user_id INTEGER NOT NULL,"
         f" plan VARCHAR(48) NOT NULL,"
         f" seats INTEGER NOT NULL,"
         f" activated_at TIMESTAMP NOT NULL,"
         f" expires_at TIMESTAMP NOT NULL,"
         f" payment_id VARCHAR(128),"
         f" order_id VARCHAR(64)"
         f")",
         'seat_subscriptions'),
        ("CREATE INDEX IF NOT EXISTS ix_seat_subs_user ON seat_subscriptions (user_id)",
         'ix_seat_subs_user'),
    ]
    for stmt, desc in stmts:
        try:
            with db.engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception as e:  # noqa: BLE001
            logger.warning('[seat_pay] DDL %s failed: %r', desc, e)


# ── Помощники (используются кабинетами) ─────────────────────────────────

def _as_dt(v):
    """expires_at может прийти строкой (SQLite) — приводим к datetime."""
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            return None
    return v


def active_seat_sub(user_id: int) -> dict | None:
    """Активная подписка на места: {plan, title, icon, seats, expires_at} или None."""
    try:
        row = db.session.execute(text(
            "SELECT plan, seats, expires_at FROM seat_subscriptions"
            " WHERE user_id = :uid AND expires_at > :now"
            " ORDER BY expires_at DESC LIMIT 1"
        ), {'uid': user_id, 'now': datetime.utcnow()}).fetchone()
    except Exception:
        db.session.rollback()
        return None
    if not row:
        return None
    info = SEAT_PLANS.get(resolve_seat_plan(row[0])) or {}
    return {
        'plan': row[0], 'seats': row[1],
        'expires_at': _as_dt(row[2]),
        'title': info.get('title', 'Подписка'),
        'icon': info.get('icon', '⭐'),
    }


def seats_used(user_id: int, role: str) -> int:
    """Занятые места: подтверждённые ученики (учитель) / дети (родитель)."""
    try:
        if role == 'teacher':
            row = db.session.execute(text(
                "SELECT COUNT(*) FROM teacher_group_members m"
                " JOIN teacher_groups g ON g.id = m.group_id"
                " WHERE g.teacher_id = :uid AND m.status = 'accepted'"
            ), {'uid': user_id}).fetchone()
        else:
            row = db.session.execute(text(
                "SELECT COUNT(*) FROM parent_child_links"
                " WHERE parent_id = :uid AND status = 'accepted'"
            ), {'uid': user_id}).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        db.session.rollback()
        return 0


def seat_gate(user_id: int, role: str) -> dict:
    """Всё для шаблонов и маршрутов: подписка + лимит мест."""
    sub = active_seat_sub(user_id)
    used = seats_used(user_id, role)
    return {
        'sub': sub,
        'used': used,
        'seats': sub['seats'] if sub else 0,
        'can_add': bool(sub and used < sub['seats']),
    }


def activate_seats_for_payment(user_id: int, plan: str,
                               payment_id=None, order_id=None) -> dict:
    """Активировать/продлить подписку на места после оплаты.

    Идемпотентно на уровне платежа: атомарный захват paid_at в
    yookassa_payments (как в premium_pay). Повторный вебхук или повторное
    открытие ссылки возврата не продлевает срок повторно.
    """
    plan = resolve_seat_plan(plan)
    if plan not in SEAT_PLANS:
        return {'ok': False, 'error': 'unknown plan'}
    info = SEAT_PLANS[plan]
    _ensure_tables()
    try:
        res = db.session.execute(text(
            "UPDATE yookassa_payments SET paid_at = :now"
            " WHERE (order_id = :oid OR payment_id = :pid) AND paid_at IS NULL"
        ), {'now': datetime.utcnow(),
            'oid': order_id or '', 'pid': payment_id or ''})
        if (res.rowcount or 0) == 0:
            row = db.session.execute(text(
                "SELECT id FROM yookassa_payments"
                " WHERE order_id = :oid OR payment_id = :pid LIMIT 1"
            ), {'oid': order_id or '', 'pid': payment_id or ''}).fetchone()
            if row:
                db.session.commit()
                return {'ok': True, 'already_applied': True}

        # Активная подписка есть → продлеваем на 30 дней от более поздней
        # даты и берём максимум мест (апгрейд тарифа).
        cur = db.session.execute(text(
            "SELECT id, expires_at, seats FROM seat_subscriptions"
            " WHERE user_id = :uid AND expires_at > :now"
            " ORDER BY expires_at DESC LIMIT 1"
        ), {'uid': user_id, 'now': datetime.utcnow()}).fetchone()
        cur_exp = _as_dt(cur[1]) if cur else None
        base = max(cur_exp, datetime.utcnow()) if cur_exp else datetime.utcnow()
        expires = base + timedelta(days=30)
        if cur:
            db.session.execute(text(
                "UPDATE seat_subscriptions SET plan = :plan, seats = :seats,"
                " expires_at = :exp, payment_id = :pid, order_id = :oid"
                " WHERE id = :id"
            ), {'plan': plan, 'seats': max(cur[2], info['seats']),
                'exp': expires, 'pid': payment_id, 'oid': order_id,
                'id': cur[0]})
        else:
            db.session.execute(text(
                "INSERT INTO seat_subscriptions"
                " (user_id, plan, seats, activated_at, expires_at, payment_id, order_id)"
                " VALUES (:uid, :plan, :seats, :now, :exp, :pid, :oid)"
            ), {'uid': user_id, 'plan': plan, 'seats': info['seats'],
                'now': datetime.utcnow(), 'exp': expires,
                'pid': payment_id, 'oid': order_id})
        db.session.commit()
        logger.info('[seat_pay] activated %s for user=%s until %s',
                    plan, user_id, expires)
        return {'ok': True, 'expires_at': expires, 'seats': info['seats'],
                'title': info['title']}
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.error('[seat_pay] activation failed user=%s: %r', user_id, e)
        return {'ok': False, 'error': str(e)}


# ── Конфиг ЮKassa (общий) ────────────────────────────────────────────────

def _yk_config() -> dict:
    try:
        from routes.yookassa_pay import get_yookassa_config
        return get_yookassa_config()
    except Exception as e:  # noqa: BLE001
        logger.warning('[seat_pay] yookassa config failed: %r', e)
        return {'configured': False, 'shop_id': '', 'secret_key': '',
                'send_receipt': False, 'is_test': False}


# ── Страница оформления ──────────────────────────────────────────────────

@seat_pay_bp.route('/payments/seats/checkout', methods=['GET'])
@login_required
def checkout():
    role = getattr(current_user, 'role', 'student') or 'student'
    if role not in ('teacher', 'parent'):
        abort(404)
    plan = resolve_seat_plan(request.args.get('plan', ''))
    if plan not in SEAT_PLANS:
        # стартовый тариф по цене (родителю с одним ребёнком — «Одно место»)
        plan = 'seat_one' if role == 'parent' else 'seat_start'
    info = SEAT_PLANS[plan]
    cfg = _yk_config()
    gate = seat_gate(current_user.id, role)
    others = [
        {'key': k, 'icon': v['icon'], 'title': v['title'],
         'price_rub': v['price_rub'], 'tagline': v['tagline'], 'seats': v['seats']}
        for k, v in SEAT_PLANS.items() if k != plan
    ]
    return render_template('payments/seat_checkout.html',
                           plan=plan, info=info, cfg=cfg, gate=gate,
                           others=others, role=role)


# ── Создание платежа ─────────────────────────────────────────────────────

@seat_pay_bp.route('/payments/seats/create', methods=['POST'])
@login_required
def create_payment():
    data = request.get_json(silent=True) or {}
    plan = resolve_seat_plan(data.get('plan') or request.form.get('plan') or '')
    role = getattr(current_user, 'role', 'student') or 'student'
    if plan not in SEAT_PLANS:
        return jsonify({'error': 'Неизвестный тариф'}), 400

    info = SEAT_PLANS[plan]
    amount = int(info['price_rub'])
    amount_str = f"{amount}.00"
    cfg = _yk_config()

    order_id = uuid.uuid4().hex
    nick_label = current_user.nickname or f"id={current_user.id}"

    # FAIL-CLOSED: сначала заказ в БД, потом платёж в ЮKassa.
    from routes.yookassa_pay import _ensure_tables as _yk_tables
    _yk_tables()
    _ensure_tables()
    try:
        db.session.execute(text(
            "INSERT INTO yookassa_payments "
            "(order_id, payment_id, user_id, item_code, amount_rub, status, confirmation_url, created_at, beneficiary_user_id) "
            "VALUES (:oid, NULL, :uid, :item, :amount, 'pending', NULL, :now, NULL)"
        ), {'oid': order_id, 'uid': current_user.id, 'item': plan,
            'amount': float(amount), 'now': datetime.utcnow()})
        db.session.commit()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.exception('[seat_pay] order insert failed: %r', e)
        return jsonify({'error': 'Не удалось сохранить заказ. Платёж не создавался — деньги не списаны. Попробуйте ещё раз.'}), 500

    # ── Демо-режим (ЮKassa не настроена): без списания ─────────────────
    if not cfg.get('configured'):
        try:
            db.session.execute(text(
                "UPDATE yookassa_payments SET payment_id = :pid, status = 'succeeded' "
                "WHERE order_id = :oid"
            ), {'pid': f"demo_{order_id[:12]}", 'oid': order_id})
            db.session.commit()
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            logger.warning('[seat_pay] demo update failed: %r', e)
        return jsonify({'ok': True, 'demo': True, 'order_id': order_id,
                        'redirect': f"/payments/seats/return?order_id={order_id}&demo=1"})

    # ── Реальный платёж ЮKassa (разовый, 30 дней) ──────────────────────
    return_url = url_for('seat_pay.payment_return', order_id=order_id, _external=True)
    payload = {
        "amount": {"value": amount_str, "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": return_url},
        "description": (
            f"Подписка «{info['title']}» на FORMYLA — {info['tagline']}"
            f" ({info['seats']} мест, 30 дней) — @{nick_label}"
        ),
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
                    "description": f"Подписка «{info['title']}» ({info['tagline']}, 30 дней)",
                    "quantity": "1.00",
                    "amount": {"value": amount_str, "currency": "RUB"},
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
        logger.exception('[seat_pay] yookassa request failed: %r', e)
        return jsonify({'error': 'Ошибка соединения с ЮKassa'}), 502

    if resp.status_code not in (200, 201):
        err = yk.get('description') or yk.get('code') or f'HTTP {resp.status_code}'
        logger.error('[seat_pay] yookassa rejected: %s', err)
        return jsonify({'error': f'ЮKassa отклонила платёж: {err}'}), 502

    confirmation_url = (yk.get('confirmation') or {}).get('confirmation_url')
    payment_id = yk.get('id')
    status = yk.get('status', 'pending')
    try:
        db.session.execute(text(
            "UPDATE yookassa_payments SET payment_id = COALESCE(:pid, payment_id), "
            "status = :st, confirmation_url = :curl WHERE order_id = :oid"
        ), {'pid': payment_id, 'st': status, 'curl': confirmation_url, 'oid': order_id})
        db.session.commit()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[seat_pay] payment row update failed order=%s: %r', order_id, e)

    if not confirmation_url:
        return jsonify({'error': 'ЮKassa не вернула ссылку на оплату'}), 502

    return jsonify({'ok': True, 'order_id': order_id, 'redirect': confirmation_url})


# ── Возврат с оплаты ─────────────────────────────────────────────────────

@seat_pay_bp.route('/payments/seats/return', methods=['GET'])
@login_required
def payment_return():
    order_id = request.args.get('order_id') or ''
    demo = request.args.get('demo') == '1'
    if not order_id:
        return redirect('/demo')

    row = None
    try:
        row = db.session.execute(text(
            "SELECT user_id, item_code, status, payment_id, amount_rub"
            " FROM yookassa_payments WHERE order_id = :oid LIMIT 1"
        ), {'oid': order_id}).fetchone()
    except Exception as e:  # noqa: BLE001
        logger.warning('[seat_pay] return lookup failed: %r', e)

    if not row:
        return render_template('payments/seat_result.html',
                               status='not_found', info=None, plan=None, role=role), 404

    p_user_id, item_code, p_status, payment_id = row[0], row[1], row[2], row[3]
    try:
        paid_amount = int(round(float(row[4]))) if row[4] is not None else None
    except (TypeError, ValueError):
        paid_amount = None
    if p_user_id != current_user.id:
        abort(403)

    plan = resolve_seat_plan(item_code) if item_code else None
    if plan not in SEAT_PLANS:
        plan = None
    info = SEAT_PLANS.get(plan) if plan else None
    role = getattr(current_user, 'role', '') or ''

    def _activate():
        return activate_seats_for_payment(current_user.id, plan, payment_id, order_id)

    if demo and p_status == 'succeeded':
        result = _activate() if plan else {'ok': False}
        sub = active_seat_sub(current_user.id)
        return render_template('payments/seat_result.html',
                               status='succeeded', info=info, plan=plan, role=role,
                               paid_amount=paid_amount, demo=True,
                               expires=str(sub['expires_at'])[:16] if sub else None,
                               seats=sub['seats'] if sub else None,
                               cabinet='/teacher' if (getattr(current_user, 'role', '') or '') == 'teacher' else '/parent')

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
            logger.warning('[seat_pay] return verify failed: %r', e)

    if p_status == 'succeeded':
        _activate() if plan else None
        sub = active_seat_sub(current_user.id)
        return render_template('payments/seat_result.html',
                               status='succeeded', info=info, plan=plan, role=role,
                               paid_amount=paid_amount,
                               expires=str(sub['expires_at'])[:16] if sub else None,
                               seats=sub['seats'] if sub else None,
                               cabinet='/teacher' if (getattr(current_user, 'role', '') or '') == 'teacher' else '/parent')

    if p_status == 'canceled':
        return render_template('payments/seat_result.html',
                               status='canceled', info=info, plan=plan, role=role, paid_amount=paid_amount)

    return render_template('payments/seat_result.html',
                           status='pending', info=info, plan=plan, role=role, paid_amount=paid_amount)


def install_seat_pay(app, register=None) -> None:
    """Регистрация blueprint'а (вызывается из routes/__init__.py)."""
    if app.extensions.get('seat_pay_installed'):
        return
    app.extensions['seat_pay_installed'] = True
    if register is None:
        app.register_blueprint(seat_pay_bp)
    else:
        register(app, seat_pay_bp)
