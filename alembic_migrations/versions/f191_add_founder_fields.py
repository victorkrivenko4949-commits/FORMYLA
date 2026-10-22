# -*- coding: utf-8 -*-
"""FOUNDERS_V1: поля Основателей и триала + founder_grants

Revision ID: f191_add_founder_fields
Revises: b1l1_add_billing_tables
Create Date: 2026-10-20

На Render это же делает services/auto_migrate.py при старте. Миграция
идемпотентна. Откат — только выдачи кампании founders_2026_v1 (флаги и
founder_grants), payments/orders/subscriptions не трогаются.
"""
import sqlalchemy as sa
from alembic import op

revision = 'f191_add_founder_fields'
down_revision = 'b1l1_add_billing_tables'
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    users_cols = {c['name'] for c in insp.get_columns('users')}
    if 'is_founder' not in users_cols:
        op.add_column('users', sa.Column('is_founder', sa.Boolean(), nullable=False,
                                         server_default=sa.text('0')))
    if 'founder_price_eligible' not in users_cols:
        op.add_column('users', sa.Column('founder_price_eligible', sa.Boolean(), nullable=False,
                                         server_default=sa.text('0')))
    if 'founder_granted_at' not in users_cols:
        op.add_column('users', sa.Column('founder_granted_at', sa.DateTime(), nullable=True))
    if 'trial_until' not in users_cols:
        op.add_column('users', sa.Column('trial_until', sa.DateTime(), nullable=True))
    tables = set(insp.get_table_names())
    if 'founder_grants' not in tables:
        op.create_table(
            'founder_grants',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('campaign_id', sa.String(40), nullable=False),
            sa.Column('amount', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('payment_id', sa.String(64), nullable=True),
            sa.Column('is_free_grant', sa.Boolean(), nullable=False, server_default=sa.text('1')),
            sa.Column('starts_at', sa.DateTime(), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('granted_at', sa.DateTime(), nullable=False),
            sa.Column('granted_by', sa.String(120), nullable=True),
            sa.Column('grant_batch', sa.Integer(), nullable=True),
            sa.UniqueConstraint('user_id', 'campaign_id', name='uq_founder_user_campaign'),
        )
        op.create_index('ix_founder_grants_user_id', 'founder_grants', ['user_id'])
        op.create_index('ix_founder_grants_campaign_id', 'founder_grants', ['campaign_id'])


def downgrade():
    """Адресный откат: выдачи кампании и флаги. Оплаченные права не трогаем."""
    op.execute("DELETE FROM founder_grants WHERE campaign_id = 'founders_2026_v1'")
    op.execute("UPDATE users SET is_founder = false, founder_price_eligible = false, "
               "founder_granted_at = NULL WHERE is_founder = true")
    # колонки и таблицу не дропаем: следующая выдача/отладка не должны терять данные
