# -*- coding: utf-8 -*-
"""Модели раздела «Задачи дня» (Daily Tasks).

3 нормализованные таблицы:

1. daily_task_sets       — один сет на пользователя на день
2. daily_task_items      — 10 задач внутри сета (position 1-10)
3. daily_generation_jobs — фоновый джоб генерации (один на пользователя на день)
"""

from datetime import datetime
from models import db


class DailyTaskSet(db.Model):
    """Один набор «Задачи дня» для пользователя на конкретную дату.

    TZ Sec 3 (document lines 144–164).
    """

    __tablename__ = 'daily_task_sets'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    target_date = db.Column(db.Date, nullable=False, index=True)
    class_level = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(32), nullable=False, default='pending')
    # status values: pending, generating, ready, failed, expired
    generated_at = db.Column(db.DateTime, nullable=True)
    triggered_by = db.Column(db.String(64), nullable=True)
    # triggered_by: 'adaptive_test', 'manual', 'cron'
    reason_summary = db.Column(db.Text, nullable=True)
    pipeline_log = db.Column(db.Text, nullable=True)
    total_cost_usd = db.Column(db.Float, nullable=False, default=0.0)

    # --- relationships ---
    user = db.relationship('User', backref=db.backref('daily_task_sets', lazy='dynamic'))
    items = db.relationship(
        'DailyTaskItem',
        back_populates='daily_set',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='DailyTaskItem.position',
    )

    __table_args__ = (
        db.UniqueConstraint('user_id', 'target_date', name='_daily_set_user_date_uc'),
    )

    def __repr__(self):
        return (
            f'<DailyTaskSet #{self.id} user={self.user_id} '
            f'date={self.target_date} status={self.status!r}>'
        )


class DailyTaskItem(db.Model):
    """Одна задача внутри сета «Задачи дня».

    TZ Sec 3 (document lines 165–207).
    """

    __tablename__ = 'daily_task_items'

    id = db.Column(db.Integer, primary_key=True)
    daily_set_id = db.Column(
        db.Integer,
        db.ForeignKey('daily_task_sets.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    position = db.Column(db.Integer, nullable=False)  # 1..10

    # --- мета-поля (заполняются на шаге Gemini) ---
    slot_kind = db.Column(db.String(32), nullable=True)
    # slot_kind: 'weakness', 'review', 'new_topic', 'mixed'
    subject = db.Column(db.String(100), nullable=True)
    topic = db.Column(db.String(200), nullable=True)
    subtopic = db.Column(db.String(100), nullable=True)
    difficulty_level = db.Column(db.Integer, nullable=True)  # 1..5
    weakness_score = db.Column(db.Float, nullable=True)
    reason = db.Column(db.Text, nullable=True)

    # --- контент (заполняется на шаге Opus) ---
    task_text = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.Text, nullable=True)
    solution = db.Column(db.Text, nullable=True)
    hints = db.Column(db.Text, nullable=True)  # JSON-строка с массивом подсказок

    # --- аудит / итерации ---
    gemini_spec_json = db.Column(db.Text, nullable=True)
    opus_iterations = db.Column(db.Integer, nullable=False, default=0)
    gpt_audit_json = db.Column(db.Text, nullable=True)
    is_flagged = db.Column(db.Boolean, nullable=False, default=False)
    flag_reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(32), nullable=False, default='pending')
    # status values: pending, approved, flagged, skipped

    # --- ответ пользователя ---
    user_answer = db.Column(db.Text, nullable=True)
    is_correct = db.Column(db.Boolean, nullable=True)
    answered_at = db.Column(db.DateTime, nullable=True)
    time_spent_seconds = db.Column(db.Integer, nullable=True)

    # --- relationships ---
    daily_set = db.relationship('DailyTaskSet', back_populates='items')

    def __repr__(self):
        return (
            f'<DailyTaskItem #{self.id} set={self.daily_set_id} '
            f'pos={self.position} status={self.status!r}>'
        )


class DailyGenerationJob(db.Model):
    """Фоновый джоб генерации «Задач дня».

    TZ Sec 3 (document lines 208–228).
    """

    __tablename__ = 'daily_generation_jobs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    target_date = db.Column(db.Date, nullable=False, index=True)
    daily_set_id = db.Column(
        db.Integer,
        db.ForeignKey('daily_task_sets.id', ondelete='SET NULL'),
        nullable=True,
    )
    state = db.Column(db.String(32), nullable=False, default='queued')
    # state values: queued, running, completed, failed
    current_step = db.Column(db.String(64), nullable=True)
    # current_step values: 'build_profile', 'gemini_plan', 'opus_generate',
    #                      'gpt_audit', 'opus_fix', 'persist'
    progress_pct = db.Column(db.Integer, nullable=False, default=0)
    error_message = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # --- relationships ---
    user = db.relationship('User', backref=db.backref('daily_generation_jobs', lazy='dynamic'))
    daily_set = db.relationship('DailyTaskSet', backref=db.backref('generation_jobs', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'target_date', name='_daily_job_user_date_uc'),
    )

    def __repr__(self):
        return (
            f'<DailyGenerationJob #{self.id} user={self.user_id} '
            f'date={self.target_date} state={self.state!r}>'
        )


class TaskPool(db.Model):
    """Общий пул сгенерированных задач (10 шт.) для повторного использования.

    Ученики с одинаковым профилем (класс + темы + floor_level) получают
    один и тот же набор из пула, без повторного вызова AI.
    """

    __tablename__ = 'task_pool'

    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(64), nullable=False, index=True)
    subject = db.Column(db.String(32), nullable=False)
    grade = db.Column(db.SmallInteger, nullable=False)
    profile_snapshot = db.Column(db.Text, nullable=False)  # JSON
    tasks = db.Column(db.Text, nullable=False)  # JSON-массив 10 задач
    specs = db.Column(db.Text, nullable=False)  # JSON-массив 10 spec'ов
    status = db.Column(db.String(16), nullable=False)
    valid_count = db.Column(db.SmallInteger, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    used_count = db.Column(db.Integer, server_default='0')
    expires_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return (
            f'<TaskPool #{self.id} key={self.cache_key[:12]}… '
            f'grade={self.grade} status={self.status!r}>'
        )


class UserTaskAssignment(db.Model):
    """Привязка пользователя к пулу — какие 5 из 10 задач он получил."""

    __tablename__ = 'user_task_assignments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    pool_id = db.Column(db.Integer, db.ForeignKey('task_pool.id'), nullable=False, index=True)
    task_positions = db.Column(db.Text, nullable=False)  # JSON-массив индексов [0,3,5,…]
    assigned_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return (
            f'<UserTaskAssignment #{self.id} user={self.user_id} '
            f'pool={self.pool_id}>'
        )
