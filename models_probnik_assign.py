# -*- coding: utf-8 -*-
"""Назначенный пробник (PROBNIK_ASSIGN_V1, 07.11.2026, владелец).

Шаблон «выдать ученику реальный вариант олимпиады на конкретный день»:
ученик видит его в задачах дня вместо обычного занятия (в том числе
вместо выходного), запускает таймер, прикладывает фото решений из
тетради (поле для текста тоже есть, краткий ответ не нужен). После сдачи
ИИ проверяет каждую задачу по шкале 0–7, считает сумму, куратор
разбирает работу (DeepSeek v4-pro с рассуждением), пишет ученику в чат
и строит план обучения.

Таблицы создаёт auto_migrate (модуль импортируется в app.py до него).
"""
from datetime import datetime

from models import db


class ProbnikAssignment(db.Model):
    __tablename__ = 'probnik_assignments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    assigned_date = db.Column(db.Date, nullable=False, index=True)

    olympiad_slug = db.Column(db.String(50), nullable=False)
    olympiad_name = db.Column(db.String(120), nullable=True)
    stage = db.Column(db.String(30), nullable=True)      # 'final' | 'qual' | ...
    grade = db.Column(db.Integer, nullable=True)
    variant_key = db.Column(db.String(200), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    # снимок задач варианта: [{num, text, solution, answer, fig_statement, fig_solution, uid}]
    tasks_json = db.Column(db.Text, nullable=False)
    used_variants_json = db.Column(db.Text, nullable=True)  # ключи, которые уже выдавались (смена)
    swaps = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    duration_minutes = db.Column(db.Integer, nullable=False, default=180, server_default='180')
    intro_text = db.Column(db.Text, nullable=True)

    # assigned → started → grading → reviewed (failed — проверка не удалась)
    status = db.Column(db.String(20), nullable=False, default='assigned',
                       server_default='assigned')
    started_at = db.Column(db.DateTime, nullable=True)
    deadline_at = db.Column(db.DateTime, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    auto_submitted = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    graded_at = db.Column(db.DateTime, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_seen_at = db.Column(db.DateTime, nullable=True)  # ученик открыл разбор (баннер-уведомление гаснет)
    grading_error = db.Column(db.Text, nullable=True)

    total_score = db.Column(db.Integer, nullable=True)
    max_score = db.Column(db.Integer, nullable=True)
    curator_review = db.Column(db.Text, nullable=True)

    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'assigned_date', name='uq_probnik_assign_user_date'),
    )


class ProbnikAssignmentAnswer(db.Model):
    """Работа ученика по одной задаче: текст + итог ИИ-проверки."""
    __tablename__ = 'probnik_assignment_answers'

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, nullable=False, index=True)
    task_idx = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=True)
    score = db.Column(db.Integer, nullable=True)
    max_score = db.Column(db.Integer, nullable=True)
    verdict = db.Column(db.String(20), nullable=True)   # full | partial | wrong | empty
    feedback = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('assignment_id', 'task_idx', name='uq_probnik_assign_answer'),
    )


class ProbnikAssignmentPhoto(db.Model):
    """Фото решения из тетради: ссылка (если хранилище есть) + распознанный текст."""
    __tablename__ = 'probnik_assignment_photos'

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, nullable=False, index=True)
    task_idx = db.Column(db.Integer, nullable=False)
    url = db.Column(db.String(500), nullable=True)
    ocr_status = db.Column(db.String(20), nullable=False, default='pending',
                           server_default='pending')   # pending | ok | failed
    ocr_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
