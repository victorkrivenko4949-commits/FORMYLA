# -*- coding: utf-8 -*-
"""Модели конструктора листка.

Таблицы: worksheets, worksheet_tasks, worksheet_assignments, worksheet_daily_items.
task_id — идентификатор записи FORMYLA_BANK.jsonl (поле ``position``,
как в services/daily_task_rotation.py: ``'task_id': t.get('position', i)``).
Банк задач не изменяется и не копируется в БД.
"""
from datetime import datetime

from models import db

WORKSHEET_MODES = ("topic", "mixed")
WORKSHEET_STATUSES = ("draft", "assigned", "closed")
TASK_ADDED_BY = ("selector", "teacher", "live_inject")
ASSIGNMENT_STATUSES = ("active", "done", "expired")


class Worksheet(db.Model):
    __tablename__ = "worksheets"

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    group_id = db.Column(db.Integer, db.ForeignKey("teacher_groups.id"), nullable=True, index=True)
    title = db.Column(db.String(200), nullable=False, default="Листок")
    grade = db.Column(db.Integer, nullable=False)
    mode = db.Column(db.String(10), nullable=False, default="topic")
    topics_json = db.Column(db.Text, nullable=False, default="[]")
    level_min = db.Column(db.Integer, nullable=False, default=1)
    level_max = db.Column(db.Integer, nullable=False, default=4)
    theory_after = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(10), nullable=False, default="draft", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.CheckConstraint("grade BETWEEN 5 AND 11", name="ck_worksheets_grade"),
        db.CheckConstraint("mode IN ('topic','mixed')", name="ck_worksheets_mode"),
        db.CheckConstraint("status IN ('draft','assigned','closed')", name="ck_worksheets_status"),
        db.CheckConstraint("level_min BETWEEN 1 AND 4 AND level_max BETWEEN 1 AND 4 AND level_min <= level_max",
                           name="ck_worksheets_levels"),
    )

    teacher = db.relationship("User", foreign_keys=[teacher_id])
    group = db.relationship("T10Group", foreign_keys=[group_id])
    tasks = db.relationship("WorksheetTask", back_populates="worksheet",
                            order_by="WorksheetTask.position",
                            cascade="all, delete-orphan", lazy="selectin")
    assignments = db.relationship("WorksheetAssignment", back_populates="worksheet",
                                  cascade="all, delete-orphan", lazy="dynamic")

    def __repr__(self):
        return f"<Worksheet #{self.id} t={self.teacher_id} g={self.grade} {self.status}>"


class WorksheetTask(db.Model):
    __tablename__ = "worksheet_tasks"

    id = db.Column(db.Integer, primary_key=True)
    worksheet_id = db.Column(db.Integer, db.ForeignKey("worksheets.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = db.Column(db.Integer, nullable=False)
    position = db.Column(db.Integer, nullable=False)
    target_level = db.Column(db.Integer, nullable=False)
    added_by = db.Column(db.String(12), nullable=False, default="selector")

    __table_args__ = (
        db.UniqueConstraint("worksheet_id", "task_id", name="uq_worksheet_tasks_ws_task"),
        db.CheckConstraint("target_level BETWEEN 1 AND 4", name="ck_worksheet_tasks_level"),
        db.CheckConstraint("added_by IN ('selector','teacher','live_inject')", name="ck_worksheet_tasks_added_by"),
    )

    worksheet = db.relationship("Worksheet", back_populates="tasks")

    def __repr__(self):
        return f"<WorksheetTask ws={self.worksheet_id} task={self.task_id} pos={self.position} L{self.target_level}>"


class WorksheetAssignment(db.Model):
    __tablename__ = "worksheet_assignments"

    id = db.Column(db.Integer, primary_key=True)
    worksheet_id = db.Column(db.Integer, db.ForeignKey("worksheets.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    assigned_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    due_at = db.Column(db.DateTime, nullable=True, index=True)
    status = db.Column(db.String(10), nullable=False, default="active")

    __table_args__ = (
        db.UniqueConstraint("worksheet_id", "student_id", name="uq_worksheet_assignments_ws_student"),
        db.CheckConstraint("status IN ('active','done','expired')", name="ck_worksheet_assignments_status"),
    )

    worksheet = db.relationship("Worksheet", back_populates="assignments")
    student = db.relationship("User", foreign_keys=[student_id])

    def __repr__(self):
        return f"<WorksheetAssignment ws={self.worksheet_id} student={self.student_id} {self.status}>"


class WorksheetDailyItem(db.Model):
    """Связь «задача листка ↔ DailyTaskItem» ученика (этап 6). Решение пишется в DailyTaskItem
    штатным потоком daily_tasks; здесь — только соответствие для ведомости и статусов."""
    __tablename__ = "worksheet_daily_items"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("worksheet_assignments.id", ondelete="CASCADE"),
                              nullable=False, index=True)
    worksheet_task_id = db.Column(db.Integer, db.ForeignKey("worksheet_tasks.id", ondelete="CASCADE"), nullable=False)
    daily_item_id = db.Column(db.Integer, nullable=False, index=True)  # daily_task_items.id (без FK: чужая таблица)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("assignment_id", "worksheet_task_id", name="uq_worksheet_daily_items_assign_task"),
    )

    def __repr__(self):
        return f"<WorksheetDailyItem a={self.assignment_id} t={self.worksheet_task_id} item={self.daily_item_id}>"
