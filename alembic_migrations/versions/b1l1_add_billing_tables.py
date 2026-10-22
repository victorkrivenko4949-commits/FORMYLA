# -*- coding: utf-8 -*-
"""BILLING_V1: orders, purchases, analytics_events

Revision ID: b1l1_add_billing_tables
Revises: a3f8c1d2e407
Create Date: 2026-10-20

На Render таблицы также создаст services/auto_migrate.py (create_all). Миграция
идемпотентна: пропускает уже существующие таблицы.
"""
from alembic import op
import sqlalchemy as sa

revision = 'b1l1_add_billing_tables'
down_revision = 'a3f8c1d2e407'
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if 'orders' not in tables:
        op.create_table(
            'orders',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('payer_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('beneficiary_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('plan_code', sa.String(40), nullable=False),
            sa.Column('amount', sa.Integer(), nullable=False),
            sa.Column('currency', sa.String(3), nullable=False, server_default='RUB'),
            sa.Column('price_version', sa.String(20), nullable=False),
            sa.Column('founder_applied', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('status', sa.String(16), nullable=False, server_default='created'),
            sa.Column('idempotence_key', sa.String(36), nullable=False),
            sa.Column('yookassa_payment_id', sa.String(64), nullable=True),
            sa.Column('confirmation_url', sa.String(500), nullable=True),
            sa.Column('is_test', sa.Boolean(), nullable=True),
            sa.Column('paid_at', sa.DateTime(), nullable=True),
            sa.Column('access_starts_at', sa.DateTime(), nullable=True),
            sa.Column('access_ends_at', sa.DateTime(), nullable=True),
            sa.Column('note', sa.String(200), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('idempotence_key', name='uq_orders_idempotence_key'),
            sa.UniqueConstraint('yookassa_payment_id', name='uq_orders_yookassa_payment_id'),
        )
        op.create_index('ix_orders_payer_user_id', 'orders', ['payer_user_id'])
        op.create_index('ix_orders_beneficiary_user_id', 'orders', ['beneficiary_user_id'])
        op.create_index('ix_orders_status', 'orders', ['status'])
        op.create_index('ix_orders_created_at', 'orders', ['created_at'])
    if 'purchases' not in tables:
        op.create_table(
            'purchases',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('order_id', sa.String(36), sa.ForeignKey('orders.id'), nullable=False, unique=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('product_code', sa.String(40), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('consumed_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_purchases_user_id', 'purchases', ['user_id'])
        op.create_index('ix_purchases_product_code', 'purchases', ['product_code'])
    if 'analytics_events' not in tables:
        op.create_table(
            'analytics_events',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('event', sa.String(40), nullable=False),
            sa.Column('order_id', sa.String(36), sa.ForeignKey('orders.id'), nullable=False, unique=True),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('plan_code', sa.String(40), nullable=True),
            sa.Column('amount', sa.Integer(), nullable=True),
            sa.Column('is_test', sa.Boolean(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('client_sent_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_analytics_events_event', 'analytics_events', ['event'])
        op.create_index('ix_analytics_events_user_id', 'analytics_events', ['user_id'])


def downgrade():
    op.drop_table('analytics_events')
    op.drop_table('purchases')
    op.drop_table('orders')
