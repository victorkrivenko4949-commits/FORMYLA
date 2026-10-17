# -*- coding: utf-8 -*-
"""BILLING_V1 — интеграция с ЮKassa (API v3) для самозанятого.

Env:
  BILLING_ENABLED=1            — витрина и webhook (0 — всё выключено)
  YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY — ключи кабинета (тестовый магазин — test_*)
  YOOKASSA_RETURN_URL=https://formyla.net/billing/success
  YOOKASSA_SKIP_IP_CHECK=0     — 1 только для локальных тестов
  YOOKASSA_API=https://api.yookassa.ru/v3

Таблицы (создаются идемпотентно): payments(payment_id UNIQUE), purchases.
Идемпотентность: повторный webhook по уже обработанному payment_id ничего не меняет.
Любая ошибка — fail-open для сайта (платёж просто не создаётся / webhook отвечает 200 и логирует).
"""
from __future__ import annotations

import base64
import ipaddress
import json
import logging
import os
import uuid
from datetime import datetime

from sqlalchemy import text

logger = logging.getLogger(__name__)

API = os.environ.get('YOOKASSA_API', 'https://api.yookassa.ru/v3')
# https://yookassa.ru/developers/using-api/webhooks#ip
YOOKASSA_NETS = [ipaddress.ip_network(n) for n in (
    '185.71.76.0/27', '185.71.77.0/27', '77.75.153.0/25', '77.75.156.11/32',
    '77.75.156.35/32', '77.75.154.128/25', '2a02:5180::/32')]


def enabled() -> bool:
    return os.environ.get('BILLING_ENABLED', '1') != '0'


def configured() -> bool:
    return bool(os.environ.get('YOOKASSA_SHOP_ID') and os.environ.get('YOOKASSA_SECRET_KEY'))


def _db():
    from models import db
    return db


def _pg() -> bool:
    try:
        return _db().engine.dialect.name == 'postgresql'
    except Exception:
        return False


_ready = False


def ensure_tables() -> None:
    global _ready
    if _ready:
        return
    db = _db()
    pg = _pg()
    serial = 'SERIAL PRIMARY KEY' if pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    ts = 'TIMESTAMP NOT NULL DEFAULT NOW()' if pg else 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP'
    stmts = [
        f"""CREATE TABLE IF NOT EXISTS payments (
                id {serial},
                payment_id VARCHAR(64) NOT NULL UNIQUE,
                user_id INTEGER,
                plan VARCHAR(40) NOT NULL,
                amount NUMERIC(10,2) NOT NULL DEFAULT 0,
                status VARCHAR(24) NOT NULL DEFAULT 'pending',
                raw_json TEXT,
                created_at {ts},
                updated_at {ts}
            )""",
        "CREATE INDEX IF NOT EXISTS ix_payments_user ON payments (user_id)",
        f"""CREATE TABLE IF NOT EXISTS purchases (
                id {serial},
                user_id INTEGER NOT NULL,
                product VARCHAR(40) NOT NULL,
                payment_id VARCHAR(64),
                amount NUMERIC(10,2) NOT NULL DEFAULT 0,
                created_at {ts},
                consumed_at TIMESTAMP
            )""",
        "CREATE INDEX IF NOT EXISTS ix_purchases_user ON purchases (user_id, product)",
    ]
    try:
        for s in stmts:
            db.session.execute(text(s))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning('yookassa.ensure_tables: %r', e)
        return
    # users.is_founder — миграция «на лету», как acq_* в services/funnel.py
    try:
        if pg:
            db.session.execute(text('ALTER TABLE users ADD COLUMN IF NOT EXISTS is_founder BOOLEAN NOT NULL DEFAULT FALSE'))
        else:
            cols = [r[1] for r in db.session.execute(text('PRAGMA table_info(users)')).fetchall()]
            if 'is_founder' not in cols:
                db.session.execute(text('ALTER TABLE users ADD COLUMN is_founder BOOLEAN NOT NULL DEFAULT 0'))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning('yookassa.ensure_tables users.is_founder: %r', e)
    _ready = True


# ──────────────────────────── HTTP ────────────────────────────
def _auth_header() -> dict:
    token = base64.b64encode(f"{os.environ.get('YOOKASSA_SHOP_ID', '')}:{os.environ.get('YOOKASSA_SECRET_KEY', '')}".encode()).decode()
    return {'Authorization': f'Basic {token}', 'Content-Type': 'application/json'}


def _http():
    import requests  # noqa: WPS433 — уже в зависимостях проекта
    return requests


def create_payment(user_id: int, plan_code: str, amount_rub: int, description: str,
                   return_url: str, extra_meta: dict | None = None) -> dict:
    """POST /payments. Возвращает объект платежа ЮKassa (нужны id и confirmation.confirmation_url)."""
    body = {
        'amount': {'value': f'{amount_rub:.2f}', 'currency': 'RUB'},
        'capture': True,
        'confirmation': {'type': 'redirect', 'return_url': return_url},
        'description': description[:128],
        'metadata': {'user_id': str(user_id), 'plan': plan_code, **{k: str(v) for k, v in (extra_meta or {}).items()}},
    }
    headers = _auth_header()
    headers['Idempotence-Key'] = str(uuid.uuid4())
    r = _http().post(f'{API}/payments', headers=headers, data=json.dumps(body), timeout=15)
    r.raise_for_status()
    data = r.json()
    _upsert_payment(data.get('id'), user_id, plan_code, amount_rub, data.get('status', 'pending'), data)
    return data


def get_payment(payment_id: str) -> dict:
    r = _http().get(f'{API}/payments/{payment_id}', headers=_auth_header(), timeout=15)
    r.raise_for_status()
    return r.json()


# ──────────────────────────── storage ────────────────────────────
def _upsert_payment(payment_id, user_id, plan, amount, status, raw) -> None:
    if not payment_id:
        return
    db = _db()
    try:
        ensure_tables()
        raw_s = json.dumps(raw, ensure_ascii=False)[:20000]
        exists = db.session.execute(text('SELECT id FROM payments WHERE payment_id = :p'), {'p': payment_id}).first()
        if exists:
            db.session.execute(text("UPDATE payments SET status = :s, raw_json = :r, updated_at = :u WHERE payment_id = :p"),
                               {'s': status, 'r': raw_s, 'u': datetime.utcnow(), 'p': payment_id})
        else:
            db.session.execute(text("""INSERT INTO payments (payment_id, user_id, plan, amount, status, raw_json)
                                       VALUES (:p, :u, :pl, :a, :s, :r)"""),
                               {'p': payment_id, 'u': user_id, 'pl': plan, 'a': amount, 's': status, 'r': raw_s})
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning('yookassa._upsert_payment: %r', e)


def payment_row(payment_id: str):
    try:
        ensure_tables()
        return _db().session.execute(text('SELECT user_id, plan, amount, status FROM payments WHERE payment_id = :p'),
                                     {'p': payment_id}).first()
    except Exception:
        _db().session.rollback()
        return None


# ──────────────────────────── webhook ────────────────────────────
def ip_allowed(remote_addr: str | None) -> bool:
    if os.environ.get('YOOKASSA_SKIP_IP_CHECK', '0') == '1':
        return True
    try:
        ip = ipaddress.ip_address((remote_addr or '').split(',')[0].strip())
    except ValueError:
        return False
    return any(ip in net for net in YOOKASSA_NETS)


def handle_notification(payload: dict, remote_addr: str | None) -> tuple[bool, str]:
    """Обработать уведомление. Возвращает (ok, reason). Идемпотентно по payment_id."""
    if not enabled():
        return False, 'disabled'
    if not ip_allowed(remote_addr):
        logger.warning('yookassa webhook from foreign ip %s', remote_addr)
        return False, 'forbidden_ip'
    obj = (payload or {}).get('object') or {}
    payment_id = obj.get('id')
    if not payment_id:
        return False, 'no_payment_id'
    row = payment_row(payment_id)
    if row and str(row[3]) == 'succeeded':
        return True, 'already_processed'
    # повторная проверка статуса у ЮKassa — защита от поддельного тела
    try:
        fresh = get_payment(payment_id)
    except Exception as e:
        logger.warning('yookassa get_payment failed %s: %r', payment_id, e)
        return False, 'verify_failed'
    status = fresh.get('status')
    meta = fresh.get('metadata') or {}
    try:
        user_id = int(meta.get('user_id') or (row[0] if row else 0) or 0)
    except (TypeError, ValueError):
        user_id = int(row[0]) if row else 0
    plan_code = meta.get('plan') or (row[1] if row else None)
    try:
        amount = float((fresh.get('amount') or {}).get('value') or (row[2] if row else 0) or 0)
    except (TypeError, ValueError):
        amount = 0.0
    _upsert_payment(payment_id, user_id or None, plan_code or '?', amount,
                    'processing' if status == 'succeeded' else (status or 'unknown'), fresh)
    if status != 'succeeded':
        return True, f'status_{status}'
    if not user_id or not plan_code:
        return True, 'succeeded_without_meta'
    ok, reason = _fulfill(user_id, plan_code, amount, payment_id, meta)
    if ok:
        _upsert_payment(payment_id, user_id, plan_code, amount, 'succeeded', fresh)
    return ok, reason


def _fulfill(user_id: int, plan_code: str, amount: float, payment_id: str, meta: dict) -> tuple[bool, str]:
    from services.billing_plans import PLANS
    p = PLANS.get(plan_code)
    if p is None:
        logger.warning('yookassa: unknown plan %s for payment %s', plan_code, payment_id)
        return True, 'unknown_plan'
    db = _db()
    try:
        if p['kind'] == 'subscription':
            from services.subscription import get_subscription_service
            get_subscription_service().activate_premium(user_id, plan=p['sub_plan'], payment_id=payment_id,
                                                        is_beta=False, amount_rub=int(round(amount)))
            db.session.commit()
        else:
            ensure_tables()
            dup = db.session.execute(text('SELECT id FROM purchases WHERE payment_id = :p'), {'p': payment_id}).first()
            if not dup:
                db.session.execute(text("""INSERT INTO purchases (user_id, product, payment_id, amount)
                                           VALUES (:u, :pr, :p, :a)"""),
                                   {'u': user_id, 'pr': plan_code, 'p': payment_id, 'a': amount})
                db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.exception('yookassa fulfil failed %s: %r', payment_id, e)
        return False, 'fulfil_failed'
    try:
        from services.funnel import payment_success
        payment_success(user_id, plan_code, amount, payment_id=payment_id,
                        props={'kind': p['kind'], 'child_user_id': meta.get('child_user_id')})
    except Exception as e:  # статистика не должна ломать оплату
        logger.warning('funnel.payment_success failed: %r', e)
    return True, 'fulfilled'
