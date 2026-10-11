# -*- coding: utf-8 -*-
"""Спринт 2, этап 1: worksheet_marks — создание, идемпотентность, уникальность, статусы."""
import pytest
from sqlalchemy.exc import IntegrityError

from models import db
from teacher.worksheets.marks import WorksheetMark, ensure_marks_for_worksheet, marks_matrix, MARK_STATUSES
from teacher.worksheets.models import Worksheet, WorksheetTask


def test_ensure_marks_creates_cross_product_and_is_idempotent(app, teacher_user, student_users):
    with app.app_context():
        db.create_all()
        ws = Worksheet(teacher_id=teacher_user.id, grade=8, title="Ведомость")
        ws.tasks.append(WorksheetTask(task_id=11, position=1, target_level=1))
        ws.tasks.append(WorksheetTask(task_id=12, position=2, target_level=2))
        db.session.add(ws); db.session.commit()
        student_ids = [s.id for s in student_users]
        assert ensure_marks_for_worksheet(ws, student_ids) == 2 * len(student_ids)
        assert ensure_marks_for_worksheet(ws, student_ids) == 0
        rows = WorksheetMark.query.filter_by(worksheet_id=ws.id).all()
        assert len(rows) == 2 * len(student_ids)
        assert all(m.status == "not_started" and not m.teacher_override and m.hints_used == 0 and m.time_spent_sec == 0 and m.attempts == 0 for m in rows)
        matrix = marks_matrix(ws)
        assert set(matrix) == set(student_ids)
        assert set(matrix[student_ids[0]]) == {11, 12}


def test_mark_unique_and_statuses(app, teacher_user, student_users):
    with app.app_context():
        db.create_all()
        ws = Worksheet(teacher_id=teacher_user.id, grade=8)
        ws.tasks.append(WorksheetTask(task_id=1, position=1, target_level=1))
        db.session.add(ws); db.session.commit()
        m = WorksheetMark(worksheet_id=ws.id, student_id=student_users[0].id, task_id=1)
        db.session.add(m); db.session.commit()
        for status in MARK_STATUSES:
            m.status = status; db.session.commit()
            assert m.status == status
        db.session.add(WorksheetMark(worksheet_id=ws.id, student_id=student_users[0].id, task_id=1))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_done_statuses(app, teacher_user, student_users):
    with app.app_context():
        db.create_all()
        ws = Worksheet(teacher_id=teacher_user.id, grade=8)
        db.session.add(ws); db.session.commit()
        for index, status in enumerate(MARK_STATUSES):
            m = WorksheetMark(worksheet_id=ws.id, student_id=student_users[0].id, task_id=100 + index, status=status)
            db.session.add(m); db.session.flush()
            assert m.is_done is (status in ("solved_self", "solved_hint", "oral_passed", "homework_done"))
        db.session.rollback()
