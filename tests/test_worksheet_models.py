# -*- coding: utf-8 -*-
"""Спринт 1, этап 1: модели конструктора листка — создание, связи, уникальность, индекс банка."""
import hashlib
import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from models import db, T10Group, T10GroupMember
from teacher.worksheets.models import Worksheet, WorksheetTask, WorksheetAssignment
from teacher.worksheets import bank_index


@pytest.fixture
def ws_group(app, teacher_user, student_users):
    with app.app_context():
        db.create_all()
        g = T10Group(name='WS group', teacher_id=teacher_user.id, invite_code='WS0001')
        db.session.add(g)
        db.session.flush()
        for s in student_users:
            db.session.add(T10GroupMember(group_id=g.id, user_id=s.id, role='student'))
        db.session.commit()
        return g.id


def test_create_worksheet_with_tasks_and_relations(app, teacher_user, ws_group):
    with app.app_context():
        ws = Worksheet(teacher_id=teacher_user.id, group_id=ws_group, title='Тест', grade=8,
                       mode='topic', topics_json='["Делимость"]')
        ws.tasks.append(WorksheetTask(task_id=101, position=1, target_level=1))
        ws.tasks.append(WorksheetTask(task_id=202, position=2, target_level=2, added_by='teacher'))
        db.session.add(ws)
        db.session.commit()

        got = db.session.get(Worksheet, ws.id)
        assert got.status == 'draft' and got.level_min == 1 and got.level_max == 4
        assert [t.task_id for t in got.tasks] == [101, 202]
        assert got.tasks[1].added_by == 'teacher'
        assert got.group.id == ws_group and got.teacher.id == teacher_user.id


def test_worksheet_task_unique_per_worksheet(app, teacher_user):
    with app.app_context():
        db.create_all()
        ws = Worksheet(teacher_id=teacher_user.id, grade=7)
        db.session.add(ws)
        db.session.flush()
        db.session.add(WorksheetTask(worksheet_id=ws.id, task_id=5, position=1, target_level=1))
        db.session.add(WorksheetTask(worksheet_id=ws.id, task_id=5, position=2, target_level=2))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_assignment_unique_per_student_and_cascade(app, teacher_user, student_users, ws_group):
    with app.app_context():
        ws = Worksheet(teacher_id=teacher_user.id, group_id=ws_group, grade=9)
        db.session.add(ws)
        db.session.flush()
        due = datetime.utcnow() + timedelta(days=3)
        db.session.add(WorksheetAssignment(worksheet_id=ws.id, student_id=student_users[0].id, due_at=due))
        db.session.commit()
        assert ws.assignments.count() == 1

        db.session.add(WorksheetAssignment(worksheet_id=ws.id, student_id=student_users[0].id, due_at=due))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        ws_id = ws.id
        ws = db.session.get(Worksheet, ws_id)
        db.session.delete(ws)
        db.session.commit()
        assert WorksheetAssignment.query.filter_by(worksheet_id=ws_id).count() == 0


def test_bank_index_builds_fast_and_is_readonly():
    before = hashlib.sha256(bank_index.BANK_PATH.read_bytes()).hexdigest() if bank_index.BANK_PATH.exists() else None
    bank_index.reset()
    t0 = time.perf_counter()
    bank_index.load()
    load_ms = (time.perf_counter() - t0) * 1000
    if not bank_index.by_id:
        pytest.skip('FORMYLA_BANK.jsonl пуст или отсутствует')
    t0 = time.perf_counter()
    for _ in range(8):
        bank_index.candidates(8, 2)
    assert (time.perf_counter() - t0) * 1000 < 300
    assert load_ms < 5000
    any_id = next(iter(bank_index.by_id))
    rec = bank_index.get(any_id)
    assert rec is not None and int(rec['position']) == any_id
    g, lvl = int(rec['grade']), int(rec['level'])
    assert rec in bank_index.by_grade_level[(g, lvl)]
    assert rec in bank_index.by_topic[rec['topic'].strip()]
    after = hashlib.sha256(bank_index.BANK_PATH.read_bytes()).hexdigest()
    assert before == after
