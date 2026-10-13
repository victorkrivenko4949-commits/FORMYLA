# -*- coding: utf-8 -*-
"""Модели «Метода недели».

method_week_sets    — один набор на пользователя на неделю (week_start = понедельник)
method_week_answers — ответы ученика на 3 задачи набора
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from models import db

logger = logging.getLogger(__name__)


class MethodWeekSet(db.Model):
    __tablename__ = 'method_week_sets'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    week_start = db.Column(db.Date, nullable=False, index=True)
    grade = db.Column(db.Integer, nullable=True)
    level = db.Column(db.Integer, nullable=True)            # уровень ученика 1..7
    method_code = db.Column(db.String(16), nullable=False)
    method_name = db.Column(db.String(200), nullable=False)
    section = db.Column(db.String(32), nullable=True)
    # status: generating | ready | failed
    status = db.Column(db.String(16), nullable=False, default='generating')
    current_step = db.Column(db.String(64), nullable=True)
    progress_pct = db.Column(db.Integer, nullable=False, default=0)
    lesson_md = db.Column(db.Text, nullable=True)           # разбор метода (Markdown+LaTeX)
    tasks_json = db.Column(db.Text, nullable=True)          # JSON-массив из 3 задач
    pipeline_log = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    total_cost_usd = db.Column(db.Float, nullable=False, default=0.0)
    model_name = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'week_start', name='_method_week_user_week_uc'),
    )

    @property
    def tasks(self):
        try:
            data = json.loads(self.tasks_json) if self.tasks_json else []
            return data if isinstance(data, list) else []
        except Exception:
            return []


class MethodWeekAnswer(db.Model):
    __tablename__ = 'method_week_answers'

    id = db.Column(db.Integer, primary_key=True)
    set_id = db.Column(db.Integer, db.ForeignKey('method_week_sets.id', ondelete='CASCADE'),
                       nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)        # 1..3
    user_answer = db.Column(db.Text, nullable=True)
    user_solution = db.Column(db.Text, nullable=True)
    is_correct = db.Column(db.Boolean, nullable=True)
    score = db.Column(db.Integer, nullable=True)
    ai_feedback = db.Column(db.Text, nullable=True)
    answered_at = db.Column(db.DateTime, nullable=True)
    time_spent_seconds = db.Column(db.Integer, nullable=True)
    xp_awarded = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        db.UniqueConstraint('set_id', 'position', name='_method_week_answer_uc'),
    )


_TABLES_READY = False


def ensure_tables() -> None:
    """Идемпотентно создаёт таблицы (SQLite и PostgreSQL). Никогда не бросает."""
    global _TABLES_READY
    if _TABLES_READY:
        return
    try:
        MethodWeekSet.__table__.create(bind=db.engine, checkfirst=True)
        MethodWeekAnswer.__table__.create(bind=db.engine, checkfirst=True)
        _TABLES_READY = True
    except Exception as exc:  # pragma: no cover
        logger.error("method_week: ensure_tables failed: %s", exc)
