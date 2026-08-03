# -*- coding: utf-8 -*-
"""schema_migration_log table — V11

Revision ID: v11_schema_migration_log
Revises: 7bcac3b72db9
Create Date: 2026-08-04

This creates the schema_migration_log table that tracks which ad-hoc
migration scripts (scripts/*migration*.py) have been applied.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'v11_schema_migration_log'
down_revision = '7bcac3b72db9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'schema_migration_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('migration_name', sa.String(length=256), nullable=False),
        sa.Column('applied_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('migration_name'),
    )
    op.create_index(
        'ix_schema_migration_log_migration_name',
        'schema_migration_log',
        ['migration_name'],
    )


def downgrade():
    op.drop_index('ix_schema_migration_log_migration_name', table_name='schema_migration_log')
    op.drop_table('schema_migration_log')
