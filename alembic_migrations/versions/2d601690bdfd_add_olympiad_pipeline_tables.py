"""add olympiad pipeline tables

Revision ID: 2d601690bdfd
Revises: 
Create Date: 2026-05-01 13:34:23.637243

Creates tables:
- olympiad_variants  (сгенерированный вариант олимпиады)
- olympiad_tasks     (одна задача в варианте)
- olympiad_task_attempts (попытка решения пользователем)

НЕ трогает существующие таблицы.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2d601690bdfd'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # --- olympiad_variants ---
    op.create_table('olympiad_variants',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('olympiad_slug', sa.String(length=100), nullable=False),
        sa.Column('olympiad_title', sa.String(length=200), nullable=True),
        sa.Column('round_key', sa.String(length=50), nullable=True),
        sa.Column('round_title', sa.String(length=200), nullable=True),
        sa.Column('grade', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('olympiad_variants', schema=None) as batch_op:
        batch_op.create_index('ix_olympiad_variants_olympiad_slug', ['olympiad_slug'], unique=False)
        batch_op.create_index('ix_olympiad_variants_grade', ['grade'], unique=False)
        batch_op.create_index('ix_olympiad_variants_user_id', ['user_id'], unique=False)

    # --- olympiad_tasks ---
    op.create_table('olympiad_tasks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('variant_id', sa.String(length=36), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('original_text', sa.Text(), nullable=True),
        sa.Column('solution', sa.Text(), nullable=True),
        sa.Column('answer', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='draft'),
        sa.Column('validation_errors', sa.Text(), nullable=True),
        sa.Column('topic', sa.String(length=100), nullable=True),
        sa.Column('source_year', sa.Integer(), nullable=True),
        sa.Column('source_problem', sa.Integer(), nullable=True),
        sa.Column('author', sa.String(length=200), nullable=True),
        sa.Column('pipeline_version', sa.String(length=10), nullable=True, server_default='1.0'),
        sa.Column('validated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['variant_id'], ['olympiad_variants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('olympiad_tasks', schema=None) as batch_op:
        batch_op.create_index('ix_olympiad_tasks_variant_id', ['variant_id'], unique=False)
        batch_op.create_index('ix_olympiad_tasks_topic', ['topic'], unique=False)
        batch_op.create_index('ix_olympiad_tasks_status', ['status'], unique=False)

    # --- olympiad_task_attempts ---
    op.create_table('olympiad_task_attempts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('answer_text', sa.Text(), nullable=True),
        sa.Column('photo_url', sa.String(length=500), nullable=True),
        sa.Column('is_correct', sa.Boolean(), nullable=True),
        sa.Column('ai_comment', sa.Text(), nullable=True),
        sa.Column('checked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['olympiad_tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('olympiad_task_attempts', schema=None) as batch_op:
        batch_op.create_index('ix_olympiad_task_attempts_task_id', ['task_id'], unique=False)
        batch_op.create_index('ix_olympiad_task_attempts_user_id', ['user_id'], unique=False)


def downgrade():
    op.drop_table('olympiad_task_attempts')
    op.drop_table('olympiad_tasks')
    op.drop_table('olympiad_variants')
