"""add worksheets, worksheet_tasks, worksheet_assignments (sprint 1, stage 1)

Revision ID: b7e2f4a9c301
Revises: v11_schema_migration_log
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa

revision = 'b7e2f4a9c301'
down_revision = 'v11_schema_migration_log'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'worksheets',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('teacher_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('teacher_groups.id'), nullable=True),
        sa.Column('title', sa.String(200), nullable=False, server_default='Листок'),
        sa.Column('grade', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(10), nullable=False, server_default='topic'),
        sa.Column('topics_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('level_min', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('level_max', sa.Integer(), nullable=False, server_default='4'),
        sa.Column('theory_after', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('status', sa.String(10), nullable=False, server_default='draft'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('grade BETWEEN 5 AND 11', name='ck_worksheets_grade'),
        sa.CheckConstraint("mode IN ('topic','mixed')", name='ck_worksheets_mode'),
        sa.CheckConstraint("status IN ('draft','assigned','closed')", name='ck_worksheets_status'),
        sa.CheckConstraint('level_min BETWEEN 1 AND 4 AND level_max BETWEEN 1 AND 4 AND level_min <= level_max',
                           name='ck_worksheets_levels'),
    )
    op.create_index('ix_worksheets_teacher_id', 'worksheets', ['teacher_id'])
    op.create_index('ix_worksheets_group_id', 'worksheets', ['group_id'])
    op.create_index('ix_worksheets_status', 'worksheets', ['status'])

    op.create_table(
        'worksheet_tasks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('worksheet_id', sa.Integer(), sa.ForeignKey('worksheets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('target_level', sa.Integer(), nullable=False),
        sa.Column('added_by', sa.String(12), nullable=False, server_default='selector'),
        sa.UniqueConstraint('worksheet_id', 'task_id', name='uq_worksheet_tasks_ws_task'),
        sa.CheckConstraint('target_level BETWEEN 1 AND 4', name='ck_worksheet_tasks_level'),
        sa.CheckConstraint("added_by IN ('selector','teacher','live_inject')", name='ck_worksheet_tasks_added_by'),
    )
    op.create_index('ix_worksheet_tasks_worksheet_id', 'worksheet_tasks', ['worksheet_id'])

    op.create_table(
        'worksheet_assignments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('worksheet_id', sa.Integer(), sa.ForeignKey('worksheets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(10), nullable=False, server_default='active'),
        sa.UniqueConstraint('worksheet_id', 'student_id', name='uq_worksheet_assignments_ws_student'),
        sa.CheckConstraint("status IN ('active','done','expired')", name='ck_worksheet_assignments_status'),
    )
    op.create_index('ix_worksheet_assignments_worksheet_id', 'worksheet_assignments', ['worksheet_id'])
    op.create_index('ix_worksheet_assignments_student_id', 'worksheet_assignments', ['student_id'])
    op.create_index('ix_worksheet_assignments_due_at', 'worksheet_assignments', ['due_at'])


def downgrade():
    op.drop_table('worksheet_assignments')
    op.drop_table('worksheet_tasks')
    op.drop_table('worksheets')
