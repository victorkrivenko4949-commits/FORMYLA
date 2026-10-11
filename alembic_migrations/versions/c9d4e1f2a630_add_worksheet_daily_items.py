"""add worksheet_daily_items (sprint 1, stage 6)

Revision ID: c9d4e1f2a630
Revises: b7e2f4a9c301
Create Date: 2026-10-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'c9d4e1f2a630'
down_revision = 'b7e2f4a9c301'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'worksheet_daily_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('assignment_id', sa.Integer(), sa.ForeignKey('worksheet_assignments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('worksheet_task_id', sa.Integer(), sa.ForeignKey('worksheet_tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('daily_item_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('assignment_id', 'worksheet_task_id', name='uq_worksheet_daily_items_assign_task'),
    )
    op.create_index('ix_worksheet_daily_items_assignment_id', 'worksheet_daily_items', ['assignment_id'])
    op.create_index('ix_worksheet_daily_items_daily_item_id', 'worksheet_daily_items', ['daily_item_id'])


def downgrade():
    op.drop_table('worksheet_daily_items')
