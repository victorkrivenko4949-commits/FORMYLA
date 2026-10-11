"""add worksheet_marks (sprint 2, stage 1)

Revision ID: e3a7b9c1d204
Revises: c9d4e1f2a630
Create Date: 2026-10-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'e3a7b9c1d204'
down_revision = 'c9d4e1f2a630'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('worksheet_marks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('worksheet_id', sa.Integer(), sa.ForeignKey('worksheets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='not_started'),
        sa.Column('teacher_override', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('hints_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('time_spent_sec', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('worksheet_id', 'student_id', 'task_id', name='uq_worksheet_marks_ws_student_task'),
        sa.CheckConstraint("status IN ('not_started','in_progress','solved_self','solved_hint','oral_passed','homework_done','failed')", name='ck_worksheet_marks_status'),
    )
    op.create_index('ix_worksheet_marks_worksheet_id', 'worksheet_marks', ['worksheet_id'])
    op.create_index('ix_worksheet_marks_student_id', 'worksheet_marks', ['student_id'])


def downgrade():
    op.drop_table('worksheet_marks')
