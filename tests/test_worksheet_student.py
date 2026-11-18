# -*- coding: utf-8 -*-
"""Спринт 1, этап 6: выдача ученику — видимость, порядок в задачах дня, смена статуса."""
import json
from datetime import date, datetime, timedelta

import pytest

from models import db, T10Group, T10GroupMember
from teacher import teacher_bp
from teacher.worksheets import bank_index
from teacher.worksheets.models import Worksheet, WorksheetTask, WorksheetAssignment, WorksheetDailyItem
from teacher.worksheets.student import expire_assignments, student_payload, sync_into_daily


@pytest.fixture
def s_app(app):
    if "teacher" not in app.blueprints:
        try:
            app.register_blueprint(teacher_bp)
        except AssertionError:
            pytest.skip("teacher_bp нельзя зарегистрировать после первого запроса")
    with app.app_context():
        db.create_all()
    return app


@pytest.fixture
def bank(tmp_path):
    recs = [{"position": i, "grade": 8, "topic": "Делимость", "level": (i % 4) + 1,
             "task_text": f"Задача листка {i}", "correct_answer": str(i), "solution": "…"} for i in range(1, 5)]
    p = tmp_path / "bank.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
    bank_index.reset(); bank_index.load(path=p)
    yield recs
    bank_index.reset()


def _mk(app, teacher_user, student, due):
    with app.app_context():
        g = T10Group(name="S6", teacher_id=teacher_user.id, invite_code="S6ABCD")
        db.session.add(g); db.session.flush()
        db.session.add(T10GroupMember(group_id=g.id, user_id=student.id, role="student"))
        ws = Worksheet(teacher_id=teacher_user.id, group_id=g.id, title="Листок S6", grade=8, status="assigned")
        for i in range(1, 5):
            ws.tasks.append(WorksheetTask(task_id=i, position=i, target_level=(i % 4) + 1))
        db.session.add(ws); db.session.flush()
        a = WorksheetAssignment(worksheet_id=ws.id, student_id=student.id, due_at=due, status="active")
        db.session.add(a); db.session.commit()
        return ws.id, a.id


def _login(client, user):
    with client.session_transaction() as s:
        s["_user_id"] = str(user.id); s["_fresh"] = True


def test_student_sees_block_after_assign(s_app, bank, teacher_user, student_users):
    ws_id, _ = _mk(s_app, teacher_user, student_users[0], datetime.utcnow() + timedelta(days=3))
    c = s_app.test_client(); _login(c, student_users[0])
    d = c.get("/api/student/worksheets").get_json()
    assert len(d["worksheets"]) == 1
    w = d["worksheets"][0]
    assert w["worksheet_id"] == ws_id and w["status"] == "active" and w["total"] == 4 and w["solved_count"] == 0
    assert "Задача листка 1" in w["tasks"][0]["statement_html"]
    r = c.get("/daily_tasks/")
    if r.status_code == 200 and r.mimetype == "text/html":
        assert b"/teacher/worksheets/static/student.js" in r.data
    assert c.get("/teacher/worksheets/static/student.js").status_code == 200


def test_sync_injects_above_adaptive(s_app, bank, teacher_user, student_users):
    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    ws_id, a_id = _mk(s_app, teacher_user, student_users[0], datetime.utcnow() + timedelta(days=3))
    with s_app.app_context():
        assert sync_into_daily(student_users[0].id)["reason"] == "no_daily_set_today"
        ds = DailyTaskSet(user_id=student_users[0].id, target_date=date.today(), class_level=8,
                          status="ready", triggered_by="test", reason_summary="t")
        db.session.add(ds); db.session.flush()
        for p in (1, 2):
            db.session.add(DailyTaskItem(daily_set_id=ds.id, position=p, slot_kind="formyla_bank", subject="math",
                                         topic="Адаптивная", difficulty_level=2, task_text=f"Адаптивная {p}",
                                         correct_answer="0", solution="…"))
        db.session.commit()
        res = sync_into_daily(student_users[0].id)
        assert res["injected"] == 4
        items = DailyTaskItem.query.filter_by(daily_set_id=ds.id).order_by(DailyTaskItem.position).all()
        assert [i.task_text for i in items][:4] == [f"Задача листка {i}" for i in range(1, 5)]
        assert all(i.position < 1 for i in items[:4])
        assert sync_into_daily(student_users[0].id)["injected"] == 0
        assert WorksheetDailyItem.query.filter_by(assignment_id=a_id).count() == 4

        for i in items[:4]:
            i.user_answer = i.correct_answer; i.is_correct = True; i.answered_at = datetime.utcnow()
        db.session.commit()
        w = student_payload(student_users[0].id)[0]
        assert w["solved_count"] == 4 and w["status"] == "done"


def test_expiry_keeps_unsolved_visible(s_app, bank, teacher_user, student_users):
    ws_id, a_id = _mk(s_app, teacher_user, student_users[0], datetime.utcnow() - timedelta(hours=1))
    with s_app.app_context():
        assert expire_assignments(student_users[0].id) == 1
        a = db.session.get(WorksheetAssignment, a_id)
        assert a.status == "expired"
        w = student_payload(student_users[0].id)[0]
        assert w["status"] == "expired" and w["overdue"] is True and w["total"] == 4
        assert sync_into_daily(student_users[0].id)["injected"] == 0
