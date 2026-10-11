# -*- coding: utf-8 -*-
"""Спринт 2, этап 1: модель отметок ведомости.

worksheet_marks — одна строка на (листок, ученик, задача банка). Создаются со статусом
not_started после успешного POST /api/teacher/worksheet/<id>/assign. Это реализовано
в after_app_request, чтобы не менять api.py из спринта 1: API сначала транзакционно
создаёт assignments, затем hook идемпотентно создаёт marks.

Статусы: not_started | in_progress | solved_self | solved_hint | oral_passed |
homework_done | failed. teacher_override=True — ручная отметка учителя; автообновление
этапа 2 её статус не трогает.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional

from flask import request
from flask_login import current_user

from models import db
from teacher import teacher_bp

MARK_STATUSES = (
    "not_started", "in_progress", "solved_self", "solved_hint",
    "oral_passed", "homework_done", "failed",
)
DONE_STATUSES = ("solved_self", "solved_hint", "oral_passed", "homework_done")


class WorksheetMark(db.Model):
    __tablename__ = "worksheet_marks"

    id = db.Column(db.Integer, primary_key=True)
    worksheet_id = db.Column(db.Integer, db.ForeignKey("worksheets.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    task_id = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="not_started")
    teacher_override = db.Column(db.Boolean, nullable=False, default=False)
    hints_used = db.Column(db.Integer, nullable=False, default=0)
    time_spent_sec = db.Column(db.Integer, nullable=False, default=0)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("worksheet_id", "student_id", "task_id", name="uq_worksheet_marks_ws_student_task"),
        db.CheckConstraint("status IN ('not_started','in_progress','solved_self','solved_hint','oral_passed','homework_done','failed')", name="ck_worksheet_marks_status"),
    )

    @property
    def is_done(self) -> bool:
        return self.status in DONE_STATUSES


def ensure_marks_for_worksheet(worksheet, student_ids: Iterable[int], commit: bool = True) -> int:
    student_ids = list(dict.fromkeys(int(s) for s in student_ids))
    if not student_ids or not worksheet.tasks:
        return 0
    existing = {(m.student_id, m.task_id) for m in WorksheetMark.query.filter(
        WorksheetMark.worksheet_id == worksheet.id, WorksheetMark.student_id.in_(student_ids)).all()}
    created = 0
    for student_id in student_ids:
        for task in worksheet.tasks:
            if (student_id, task.task_id) not in existing:
                db.session.add(WorksheetMark(worksheet_id=worksheet.id, student_id=student_id, task_id=task.task_id))
                created += 1
    if created and commit:
        db.session.commit()
    return created


def marks_matrix(worksheet, student_ids: Optional[List[int]] = None) -> Dict[int, Dict[int, WorksheetMark]]:
    q = WorksheetMark.query.filter_by(worksheet_id=worksheet.id)
    if student_ids is not None:
        q = q.filter(WorksheetMark.student_id.in_(student_ids))
    out: Dict[int, Dict[int, WorksheetMark]] = {}
    for mark in q.all():
        out.setdefault(mark.student_id, {})[mark.task_id] = mark
    return out


@teacher_bp.after_app_request
def _create_marks_after_assignment(response):
    try:
        if (request.method != "POST" or response.status_code >= 400 or not request.path.startswith("/api/teacher/worksheet/") or not request.path.endswith("/assign") or (getattr(current_user, "role", "student") or "student") != "teacher"):
            return response
        ws_id = int(request.path.split("/")[4])
        from teacher.worksheets.models import Worksheet
        ws = db.session.get(Worksheet, ws_id)
        if ws is None or ws.teacher_id != current_user.id:
            return response
        created = ensure_marks_for_worksheet(ws, [a.student_id for a in ws.assignments.all()])
        response.headers["X-Worksheet-Marks-Created"] = str(created)
    except Exception:
        db.session.rollback()
    return response
