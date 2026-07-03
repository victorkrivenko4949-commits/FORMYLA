# -*- coding: utf-8 -*-
"""Модели модуля «Куратор» (AI-наставник).

4 таблицы:
  1. student_diagnostics  — результаты входного тестирования
  2. learning_plans       — персональные учебные планы
  3. task_attempts        — попытки решения задач
  4. progress_log         — лог прогресса (ежедневные/еженедельные срезы)
"""

from datetime import datetime, date
from models import db


class StudentDiagnostic(db.Model):
    """Результаты диагностического тестирования ученика.

    После прохождения адаптивного теста формируется профиль:
    - Уровень по каждой теме (0-100%)
    - Общий уровень
    - История ответов
    """

    __tablename__ = 'student_diagnostics'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    session_id = db.Column(db.String(64), nullable=True, index=True)
    grade = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(32), nullable=False, default='pending')
    # status: pending, in_progress, completed, failed

    # JSON: профиль по темам
    # {"algebra": {"pct": 45, "level": 1, "tasks_correct": 3, "tasks_total": 5}, ...}
    profile_json = db.Column(db.Text, nullable=True)

    # Общий уровень (0-100)
    overall_pct = db.Column(db.Integer, nullable=False, default=0)
    total_questions = db.Column(db.Integer, nullable=False, default=0)
    correct_answers = db.Column(db.Integer, nullable=False, default=0)

    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    # JSON: история вопросов [{"task_id": ..., "topic": ..., "answer": ..., "is_correct": ..., "time_spent": ...}]
    question_log = db.Column(db.Text, nullable=True)

    # AI-резюме (текст от DeepSeek)
    ai_summary = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # --- relationships ---
    user = db.relationship('User', backref=db.backref('student_diagnostics', lazy='dynamic'))

    def __repr__(self):
        return (
            f'<StudentDiagnostic #{self.id} user={self.user_id} '
            f'status={self.status!r} overall={self.overall_pct}%>'
        )

    @property
    def profile(self):
        """Возвращает profile_json как dict."""
        import json
        if not self.profile_json:
            return {}
        try:
            return json.loads(self.profile_json)
        except (json.JSONDecodeError, TypeError):
            return {}

    @profile.setter
    def profile(self, data: dict):
        import json
        self.profile_json = json.dumps(data, ensure_ascii=False)

    @property
    def question_log_list(self):
        """Возвращает question_log как list."""
        import json
        if not self.question_log:
            return []
        try:
            return json.loads(self.question_log)
        except (json.JSONDecodeError, TypeError):
            return []

    @question_log_list.setter
    def question_log_list(self, data: list):
        import json
        self.question_log = json.dumps(data, ensure_ascii=False)


class LearningPlan(db.Model):
    """Персональный учебный план (roadmap) ученика.

    Создаётся после диагностики. Содержит понедельный план
    с учётом слабых тем и даты целевой олимпиады.
    """

    __tablename__ = 'learning_plans'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=True)
    goal = db.Column(db.Text, nullable=True)
    plan_type = db.Column(db.String(32), nullable=False, default='diagnostic')
    # plan_type: diagnostic, manual

    # JSON: копия профиля из диагностики
    baseline_profile = db.Column(db.Text, nullable=True)

    start_date = db.Column(db.Date, nullable=True)
    target_date = db.Column(db.Date, nullable=True)
    target_olympiad = db.Column(db.String(255), nullable=True)
    target_stage = db.Column(db.String(64), nullable=True)

    status = db.Column(db.String(32), nullable=False, default='active')
    # status: active, paused, completed, archived

    # JSON: roadmap по неделям
    # [{"week": 1, "topics": [...], "goal": "...", "tasks_count": 5, "focus": "weakest"}, ...]
    roadmap_json = db.Column(db.Text, nullable=True)

    # JSON: текущий профиль (обновляется по мере прогресса)
    current_profile = db.Column(db.Text, nullable=True)

    total_weeks = db.Column(db.Integer, nullable=False, default=0)
    current_week = db.Column(db.Integer, nullable=False, default=0)

    # JSON: приоритеты тем (список topic_key от слабой к сильной)
    topic_priorities = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.utcnow)

    # --- relationships ---
    user = db.relationship('User', backref=db.backref('learning_plans', lazy='dynamic'))
    attempts = db.relationship(
        'CuratorTaskAttempt',
        back_populates='plan',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )
    progress_logs = db.relationship(
        'ProgressLog',
        back_populates='plan',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def __repr__(self):
        return (
            f'<LearningPlan #{self.id} user={self.user_id} '
            f'status={self.status!r} week={self.current_week}/{self.total_weeks}>'
        )

    @property
    def roadmap(self):
        """Возвращает roadmap_json как list."""
        import json
        if not self.roadmap_json:
            return []
        try:
            return json.loads(self.roadmap_json)
        except (json.JSONDecodeError, TypeError):
            return []

    @roadmap.setter
    def roadmap(self, data: list):
        import json
        self.roadmap_json = json.dumps(data, ensure_ascii=False)

    @property
    def current_profile_dict(self):
        """Возвращает current_profile как dict."""
        import json
        if not self.current_profile:
            return {}
        try:
            return json.loads(self.current_profile)
        except (json.JSONDecodeError, TypeError):
            return {}

    @current_profile_dict.setter
    def current_profile_dict(self, data: dict):
        import json
        self.current_profile = json.dumps(data, ensure_ascii=False)

    @property
    def topic_priorities_list(self):
        """Возвращает topic_priorities как list."""
        import json
        if not self.topic_priorities:
            return []
        try:
            return json.loads(self.topic_priorities)
        except (json.JSONDecodeError, TypeError):
            return []

    @topic_priorities_list.setter
    def topic_priorities_list(self, data: list):
        import json
        self.topic_priorities = json.dumps(data, ensure_ascii=False)

    @property
    def days_until_target(self):
        """Количество дней до целевой олимпиады."""
        if not self.target_date:
            return None
        delta = self.target_date - date.today()
        return delta.days


class CuratorTaskAttempt(db.Model):
    """Попытка решения задачи учеником.

    Фиксирует каждую попытку: ответ, время, подсказки, AI-фидбек.
    """

    __tablename__ = 'task_attempts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    # ID задачи из TaskBank (или другой таблицы)
    task_id = db.Column(db.Integer, nullable=True, index=True)
    # Источник: adaptive, daily_task, curator_plan, manual
    task_source = db.Column(db.String(32), nullable=False, default='curator_plan')
    # Тип: diagnostic, practice, test, hint
    task_type = db.Column(db.String(32), nullable=False, default='practice')

    plan_id = db.Column(
        db.Integer,
        db.ForeignKey('learning_plans.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )

    topic = db.Column(db.String(100), nullable=True, index=True)
    difficulty = db.Column(db.Integer, nullable=True)

    # Ответ ученика
    user_answer = db.Column(db.Text, nullable=True)
    correct_answer = db.Column(db.Text, nullable=True)
    is_correct = db.Column(db.Boolean, nullable=True)

    attempts_count = db.Column(db.Integer, nullable=False, default=1)
    time_spent_sec = db.Column(db.Integer, nullable=True)

    used_hints = db.Column(db.Boolean, nullable=False, default=False)
    hints_shown = db.Column(db.Integer, nullable=False, default=0)
    # Количество различных подсказок, которые ученик действительно открыл
    hints_used = db.Column(db.Integer, nullable=False, default=0)

    # AI-фидбек (JSON от tutor)
    ai_feedback = db.Column(db.Text, nullable=True)
    # Оценка метода (0.0-1.0)
    method_score = db.Column(db.Float, nullable=True)

    attempted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # --- relationships ---
    user = db.relationship('User', backref=db.backref('task_attempts', lazy='dynamic'))
    plan = db.relationship('LearningPlan', back_populates='attempts')

    def __repr__(self):
        return (
            f'<CuratorTaskAttempt #{self.id} user={self.user_id} '
            f'task={self.task_id} correct={self.is_correct}>'
        )

    @property
    def ai_feedback_dict(self):
        """Возвращает ai_feedback как dict."""
        import json
        if not self.ai_feedback:
            return {}
        try:
            return json.loads(self.ai_feedback)
        except (json.JSONDecodeError, TypeError):
            return {}

    @ai_feedback_dict.setter
    def ai_feedback_dict(self, data: dict):
        import json
        self.ai_feedback = json.dumps(data, ensure_ascii=False)


class ProgressLog(db.Model):
    """Лог прогресса ученика.

    Срезы: ежедневные, еженедельные, после сессий.
    Используется для:
    - Отслеживания динамики уровня по темам
    - Выявления "застреваний" (3+ дня без прогресса)
    - Расчёта серий (streaks)
    - AI-советов
    """

    __tablename__ = 'progress_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    plan_id = db.Column(
        db.Integer,
        db.ForeignKey('learning_plans.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )

    log_date = db.Column(db.Date, nullable=False, index=True)
    log_type = db.Column(db.String(16), nullable=False, default='daily')
    # log_type: daily, weekly, session

    # JSON: профиль на момент среза {topic: pct}
    profile_snapshot = db.Column(db.Text, nullable=True)

    tasks_solved = db.Column(db.Integer, nullable=False, default=0)
    tasks_total = db.Column(db.Integer, nullable=False, default=0)
    accuracy_pct = db.Column(db.Float, nullable=True)

    minutes_spent = db.Column(db.Float, nullable=True)

    # Серия (streak)
    streak_days = db.Column(db.Integer, nullable=False, default=0)
    max_streak = db.Column(db.Integer, nullable=False, default=0)

    plan_week = db.Column(db.Integer, nullable=True)

    # Флаг застревания
    is_stuck = db.Column(db.Boolean, nullable=False, default=False)

    # AI-совет (краткий)
    ai_advice = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # --- relationships ---
    user = db.relationship('User', backref=db.backref('progress_logs', lazy='dynamic'))
    plan = db.relationship('LearningPlan', back_populates='progress_logs')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'log_date', 'log_type', name='_pl_user_date_type_uc'),
    )

    def __repr__(self):
        return (
            f'<ProgressLog #{self.id} user={self.user_id} '
            f'date={self.log_date} type={self.log_type!r} '
            f'streak={self.streak_days} accuracy={self.accuracy_pct}>'
        )

    @property
    def profile_snapshot_dict(self):
        """Возвращает profile_snapshot как dict."""
        import json
        if not self.profile_snapshot:
            return {}
        try:
            return json.loads(self.profile_snapshot)
        except (json.JSONDecodeError, TypeError):
            return {}

    @profile_snapshot_dict.setter
    def profile_snapshot_dict(self, data: dict):
        import json
        self.profile_snapshot = json.dumps(data, ensure_ascii=False)
