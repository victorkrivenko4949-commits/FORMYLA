# -*- coding: utf-8 -*-
"""BILLING_V1 — модели заказов ЮKassa (orders, purchases, analytics_events).

Импортируется из routes/billing.py при установке blueprint, поэтому
services/auto_migrate.py создаёт таблицы автоматически (create_all для
отсутствующих таблиц). Параллельно есть Alembic-миграция
alembic_migrations/versions/b1l1_add_billing_tables.py.

Все моменты времени — naive UTC (как и в остальных моделях проекта).
Суммы — целые копейки.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from models import db


def _uuid() -> str:
    return str(uuid.uuid4())


ORDER_STATUSES = ('created', 'pending', 'paid', 'failed', 'expired')


class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    payer_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    beneficiary_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    plan_code = db.Column(db.String(40), nullable=False)
    amount = db.Column(db.Integer, nullable=False)              # копейки
    currency = db.Column(db.String(3), nullable=False, default='RUB', server_default='RUB')
    price_version = db.Column(db.String(20), nullable=False)
    founder_applied = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    status = db.Column(db.String(16), nullable=False, default='created', server_default='created', index=True)
    idempotence_key = db.Column(db.String(36), nullable=False, unique=True, default=_uuid)
    yookassa_payment_id = db.Column(db.String(64), nullable=True, unique=True)
    confirmation_url = db.Column(db.String(500), nullable=True)
    is_test = db.Column(db.Boolean, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    access_starts_at = db.Column(db.DateTime, nullable=True)
    access_ends_at = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.String(200), nullable=True)            # причина mismatch/failed, без payload
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Order {self.id} {self.plan_code} {self.status}>'


class Purchase(db.Model):
    """Разовые покупки (probe_once, sheet_once, method_week_once)."""
    __tablename__ = 'purchases'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(36), db.ForeignKey('orders.id'), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    product_code = db.Column(db.String(40), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    consumed_at = db.Column(db.DateTime, nullable=True)


class AnalyticsEvent(db.Model):
    """Серверные события монетизации. order_id уникален → одно payment_success на заказ."""
    __tablename__ = 'analytics_events'

    id = db.Column(db.Integer, primary_key=True)
    event = db.Column(db.String(40), nullable=False, index=True)
    order_id = db.Column(db.String(36), db.ForeignKey('orders.id'), nullable=False, unique=True)
    user_id = db.Column(db.Integer, nullable=True, index=True)
    plan_code = db.Column(db.String(40), nullable=True)
    amount = db.Column(db.Integer, nullable=True)
    is_test = db.Column(db.Boolean, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    client_sent_at = db.Column(db.DateTime, nullable=True)     # когда браузерная цель Метрики отдана
