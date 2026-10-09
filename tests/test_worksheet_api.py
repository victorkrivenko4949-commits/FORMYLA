# -*- coding: utf-8 -*-
"""Спринт 1, этап 3: контракты и права API конструктора листка."""
import json
from datetime import datetime, timedelta

import pytest

from models import db, T10Group, T10GroupMember
from teacher import teacher_bp
from teacher.worksheets import bank_index, history
from teacher.worksheets.models import Worksheet, WorksheetAssignment


def _rec(pos, grade, topic, level, oly, year):
    return {"position": pos, "grade": grade, "topic": topic, "level": level, "olympiad": oly, "year": year,
            "task_text": f"Задача {pos}: x^2 ({topic}, L{level})", "correct_answer": "1", "solution": "…"}


@pytest.fixture
def api_app(app):
    if "teacher" not in app.blueprints:
        try:
            app.register_blueprint(teacher_bp)
        except AssertionError:
            pytest.skip("teacher_bp нельзя зарегистрировать после первого запроса — зарегистрируйте в conftest")
    with app.app_context():
        db.create_all()
    return app


@pytest.fixture
def bank(tmp_path, monkeypatch):
    recs, pos = [], 1
    oly = [("ВсОШ", 2021), ("ВсОШ", 2022), ("Матпраздник", 2022), ("Турнир городов", 2023), (None, None)]
    for topic in ("Делимость", "Комбинаторика"):
        for level in (1, 2, 3, 4):
            for k in range(6):
                recs.append(_rec(pos, 8, topic, level, *oly[k % len(oly)])); pos += 1
    p = tmp_path / "bank.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
    bank_index.reset(); bank_index.load(path=p)
    monkeypatch.setattr(history, "group_solved_task_ids", lambda gid: set())
    monkeypatch.setattr(history, "group_recent_worksheet_task_ids", lambda gid, days=60: set())
    yield recs
    bank_index.reset()


@pytest.fixture
def group(api_app, teacher_user, student_users):
    with api_app.app_context():
        g = T10Group(name="API group", teacher_id=teacher_user.id, invite_code="API001")
        db.session.add(g); db.session.flush()
        for s in student_users:
            db.session.add(T10GroupMember(group_id=g.id, user_id=s.id, role="student"))
        db.session.commit()
        return g.id


def _login(client, user):
    with client.session_transaction() as s:
        s["_user_id"] = str(user.id)
        s["_fresh"] = True


def _gen(client, **over):
    body = {"grade": 8, "topics": ["Делимость", "Комбинаторика"], "n": 8, "seed": 1}
    body.update(over)
    return client.post("/api/teacher/worksheet/generate", json=body)


def test_generate_contract(api_app, bank, teacher_user, group):
    c = api_app.test_client(); _login(c, teacher_user)
    r = _gen(c, group_id=group)
    assert r.status_code == 201, r.get_json()
    d = r.get_json()
    assert set(d) >= {"worksheet_id", "tasks", "warnings", "status"}
    assert d["status"] == "draft" and len(d["tasks"]) == 8
    t = d["tasks"][0]
    assert set(t) >= {"position", "task_id", "level", "topic", "methods", "source", "statement_html", "has_figure"}
    assert [x["position"] for x in d["tasks"]] == list(range(1, 9))
    assert sorted(x["target_level"] for x in d["tasks"]) == [x["target_level"] for x in d["tasks"]]


def test_generate_requires_teacher(api_app, bank, student_users):
    c = api_app.test_client(); _login(c, student_users[0])
    assert _gen(c).status_code == 403
    assert api_app.test_client().post("/api/teacher/worksheet/generate", json={"grade": 8}).status_code in (401, 302)


def test_generate_rejects_foreign_group(api_app, bank, teacher_user, student_users):
    with api_app.app_context():
        other = T10Group(name="Foreign", teacher_id=student_users[0].id, invite_code="FOR001")
        db.session.add(other); db.session.commit(); oid = other.id
    c = api_app.test_client(); _login(c, teacher_user)
    assert _gen(c, group_id=oid).status_code == 403


def test_replace_patch_duplicate(api_app, bank, teacher_user):
    c = api_app.test_client(); _login(c, teacher_user)
    d = _gen(c).get_json(); wid = d["worksheet_id"]
    victim = next(t for t in d["tasks"] if t["level"] == 2)

    r = c.post(f"/api/teacher/worksheet/{wid}/replace_task", json={"task_id": victim["task_id"], "direction": "harder", "seed": 1})
    assert r.status_code == 200, r.get_json()
    new = r.get_json()["task"]
    assert new["level"] == 3 and new["task_id"] != victim["task_id"] and new["added_by"] == "teacher"

    r = c.patch(f"/api/teacher/worksheet/{wid}", json={"title": "Новое", "theory_after": True, "remove_task_id": new["task_id"]})
    assert r.status_code == 200
    d2 = r.get_json()
    assert d2["title"] == "Новое" and d2["theory_after"] is True and len(d2["tasks"]) == 7
    assert [t["position"] for t in d2["tasks"]] == list(range(1, 8))

    ids = [t["task_id"] for t in d2["tasks"]][::-1]
    r = c.patch(f"/api/teacher/worksheet/{wid}", json={"order": ids})
    assert r.status_code == 200 and [t["task_id"] for t in r.get_json()["tasks"]] == ids
    assert c.patch(f"/api/teacher/worksheet/{wid}", json={"order": ids[:-1]}).status_code == 400

    r = c.post(f"/api/teacher/worksheet/{wid}/duplicate")
    assert r.status_code == 201
    dup = r.get_json()
    assert dup["worksheet_id"] != wid and dup["status"] == "draft" and len(dup["tasks"]) == 7
    assert [t["task_id"] for t in dup["tasks"]] == ids


def test_assign_and_list(api_app, bank, teacher_user, student_users, group):
    c = api_app.test_client(); _login(c, teacher_user)
    wid = _gen(c, group_id=group).get_json()["worksheet_id"]
    due = (datetime.utcnow() + timedelta(days=5)).replace(microsecond=0).isoformat()
    r = c.post(f"/api/teacher/worksheet/{wid}/assign", json={"group_id": group, "due_at": due})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["status"] == "assigned" and r.get_json()["assigned"] == len(student_users)
    with api_app.app_context():
        rows = WorksheetAssignment.query.filter_by(worksheet_id=wid).all()
        assert {a.student_id for a in rows} == {s.id for s in student_users}
        assert all(a.status == "active" for a in rows)
        assert db.session.get(Worksheet, wid).status == "assigned"
    assert c.post(f"/api/teacher/worksheet/{wid}/assign", json={"group_id": group, "due_at": due}).get_json()["created"] == 0
    assert c.post(f"/api/teacher/worksheet/{wid}/assign", json={"group_id": group}).status_code == 400

    r = c.get(f"/api/teacher/worksheets?group_id={group}&status=assigned")
    assert r.status_code == 200
    lst = r.get_json()["worksheets"]
    assert any(w["worksheet_id"] == wid for w in lst) and all(w["status"] == "assigned" for w in lst)
    drafts = c.get("/api/teacher/worksheets?status=draft").get_json()["worksheets"]
    assert all(w["status"] == "draft" for w in drafts)


def test_foreign_worksheet_403(api_app, bank, teacher_user, student_users):
    c = api_app.test_client(); _login(c, teacher_user)
    wid = _gen(c).get_json()["worksheet_id"]
    with api_app.app_context():
        u = db.session.get(type(student_users[0]), student_users[0].id)
        old = u.role; u.role = "teacher"; db.session.commit()
    try:
        c2 = api_app.test_client(); _login(c2, student_users[0])
        assert c2.get(f"/api/teacher/worksheet/{wid}").status_code == 403
        assert c2.patch(f"/api/teacher/worksheet/{wid}", json={"title": "x"}).status_code == 403
        assert c2.post(f"/api/teacher/worksheet/{wid}/replace_task", json={"task_id": 1}).status_code == 403
        assert c2.post(f"/api/teacher/worksheet/{wid}/assign", json={"group_id": 1, "due_at": "2030-01-01T00:00:00"}).status_code == 403
        assert c2.post(f"/api/teacher/worksheet/{wid}/duplicate").status_code == 403
        assert c2.get("/api/teacher/worksheet/999999").status_code == 404
    finally:
        with api_app.app_context():
            u = db.session.get(type(student_users[0]), student_users[0].id); u.role = old; db.session.commit()
