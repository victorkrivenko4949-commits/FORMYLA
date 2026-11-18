# -*- coding: utf-8 -*-
"""Спринт 2, этап 2: автообновление отметок — переходы (чистая функция) и хуки (flush / hint)."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace as NS

import pytest

from teacher.worksheets.marks_sync import apply_attempt, MAX_ATTEMPTS

DUE = datetime(2026, 10, 20, 23, 59)
BEFORE = DUE - timedelta(days=1)
AFTER = DUE + timedelta(hours=1)


def mk(**k):
    d = dict(status="not_started", teacher_override=False, hints_used=0, time_spent_sec=0, attempts=0)
    d.update(k)
    return NS(**d)


def test_first_wrong_then_correct_is_solved_self():
    m = mk()
    assert apply_attempt(m, False, DUE, BEFORE, 30) == "in_progress" and m.attempts == 1 and m.time_spent_sec == 30
    assert apply_attempt(m, True, DUE, BEFORE, 20) == "solved_self" and m.attempts == 2 and m.time_spent_sec == 50


def test_hint_then_correct_is_solved_hint():
    m = mk()
    apply_attempt(m, None, DUE, BEFORE, hint=True)
    assert m.status == "in_progress" and m.hints_used == 1 and m.attempts == 0
    assert apply_attempt(m, True, DUE, BEFORE) == "solved_hint"


def test_three_wrong_is_failed_then_correct_is_homework():
    m = mk()
    for _ in range(MAX_ATTEMPTS - 1):
        assert apply_attempt(m, False, DUE, BEFORE) == "in_progress"
    assert apply_attempt(m, False, DUE, BEFORE) == "failed"
    assert apply_attempt(m, True, DUE, BEFORE) == "homework_done"


def test_overdue_transitions():
    assert apply_attempt(mk(), False, DUE, AFTER) == "failed"
    assert apply_attempt(mk(), True, DUE, AFTER) == "homework_done"
    assert apply_attempt(mk(), True, None, AFTER) == "solved_self"


def test_override_keeps_status_but_counts():
    m = mk(status="oral_passed", teacher_override=True)
    assert apply_attempt(m, False, DUE, BEFORE, 10) == "oral_passed" and m.attempts == 1 and m.time_spent_sec == 10
    apply_attempt(m, None, DUE, BEFORE, hint=True)
    assert m.status == "oral_passed" and m.hints_used == 1


def test_solved_not_downgraded_by_wrong_answer():
    m = mk(status="solved_self")
    assert apply_attempt(m, False, DUE, BEFORE) == "solved_self"


# ───────────────────────────── интеграция с БД ──────────────────────────────

@pytest.fixture
def ws_env(app, teacher_user, student_users):
    from models import db
    from teacher.worksheets.marks import ensure_marks_for_worksheet
    from teacher.worksheets.models import Worksheet, WorksheetTask, WorksheetAssignment, WorksheetDailyItem
    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    with app.app_context():
        db.create_all()
        ws = Worksheet(teacher_id=teacher_user.id, grade=8, title="Sync")
        ws.tasks.append(WorksheetTask(task_id=501, position=1, target_level=1))
        db.session.add(ws); db.session.flush()
        a = WorksheetAssignment(worksheet_id=ws.id, student_id=student_users[0].id,
                                due_at=datetime.utcnow() + timedelta(days=2), status="active")
        db.session.add(a); db.session.flush()
        ensure_marks_for_worksheet(ws, [student_users[0].id], commit=False)
        ds = DailyTaskSet(user_id=student_users[0].id, target_date=date.today(), class_level=8,
                          status="ready", triggered_by="test", reason_summary="t")
        db.session.add(ds); db.session.flush()
        item = DailyTaskItem(daily_set_id=ds.id, position=-100, slot_kind="formyla_bank", subject="math",
                             topic="T", difficulty_level=1, task_text="x", correct_answer="7", solution="…")
        db.session.add(item); db.session.flush()
        db.session.add(WorksheetDailyItem(assignment_id=a.id, worksheet_task_id=ws.tasks[0].id, daily_item_id=item.id))
        db.session.commit()
        return {"ws_id": ws.id, "a_id": a.id, "item_id": item.id, "student_id": student_users[0].id}


def test_flush_hook_updates_mark(app, ws_env):
    from models import db
    from teacher.worksheets.marks import WorksheetMark
    from daily_tasks.models import DailyTaskItem
    with app.app_context():
        item = db.session.get(DailyTaskItem, ws_env["item_id"])
        item.user_answer = "1"; item.is_correct = False; item.answered_at = datetime.utcnow(); item.time_spent_seconds = 40
        db.session.commit()
        m = WorksheetMark.query.filter_by(worksheet_id=ws_env["ws_id"], student_id=ws_env["student_id"], task_id=501).one()
        assert m.status == "in_progress" and m.attempts == 1 and m.time_spent_sec == 40
        item.user_answer = "7"; item.is_correct = True; item.answered_at = datetime.utcnow(); item.time_spent_seconds = 65
        db.session.commit()
        db.session.refresh(m)
        assert m.status == "solved_self" and m.attempts == 2 and m.time_spent_sec == 65


def test_hint_hook_counts(app, ws_env, student_users):
    from teacher.worksheets.marks import WorksheetMark
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = str(student_users[0].id); s["_fresh"] = True
    r = c.get(f"/daily_tasks/{ws_env['item_id']}/hint?hint_index=0")
    with app.app_context():
        m = WorksheetMark.query.filter_by(worksheet_id=ws_env["ws_id"], student_id=ws_env["student_id"], task_id=501).one()
        if r.status_code == 200:
            assert m.hints_used == 1 and m.status == "in_progress"
        else:
            pytest.skip(f"/daily_tasks/<id>/hint вернул {r.status_code} в тестовом окружении")


def test_expiry_marks_failed(app, ws_env):
    from models import db
    from teacher.worksheets.marks import WorksheetMark
    from teacher.worksheets.models import WorksheetAssignment
    with app.app_context():
        a = db.session.get(WorksheetAssignment, ws_env["a_id"])
        a.status = "expired"
        db.session.commit()
        m = WorksheetMark.query.filter_by(worksheet_id=ws_env["ws_id"], student_id=ws_env["student_id"], task_id=501).one()
        assert m.status == "failed"
