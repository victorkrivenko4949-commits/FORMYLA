# -*- coding: utf-8 -*-
"""add parent_child_links table

Родитель↔ребёнок: запрос на привязку с подтверждением ребёнком
( pending / accepted / rejected / blocked ).

Revision ID: a3f8c1d2e407
Revises: 2d601690bdfd
Create Date: 2026-09-26
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3f8c1d2e407'
down_revision = '2d601690bdfd'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'parent_child_links' in inspector.get_table_names():
        return
    op.create_table(
        'parent_child_links',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('parent_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('child_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('responded_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('parent_id', 'child_id', name='_parent_child_unique'),
        sa.CheckConstraint('parent_id != child_id', name='_no_self_parent_child'),
    )
    op.create_index('ix_parent_child_links_parent_id', 'parent_child_links', ['parent_id'])
    op.create_index('ix_parent_child_links_child_id', 'parent_child_links', ['child_id'])
    op.create_index('ix_parent_child_links_status', 'parent_child_links', ['status'])


def downgrade():
    op.drop_index('ix_parent_child_links_status', table_name='parent_child_links')
    op.drop_index('ix_parent_child_links_child_id', table_name='parent_child_links')
    op.drop_index('ix_parent_child_links_parent_id', table_name='parent_child_links')
    op.drop_table('parent_child_links')
