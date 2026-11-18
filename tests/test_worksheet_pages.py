# -*- coding: utf-8 -*-
"""Спринт 1, этап 4: страницы конструктора (рендер, права, topics)."""
import json

import pytest

from teacher import teacher_bp
from teacher.worksheets import bank_index


@pytest.fixture
def page_app(app):
    if "teacher" not in app.blueprints:
        try:
            app.register_blueprint(teacher_bp)
        except AssertionError:
            pytest.skip("teacher_bp нельзя зарегистрировать после первого запроса")
    return app


@pytest.fixture
def bank(tmp_path):
    recs = [{"position": i, "grade": 8, "topic": "Делимость" if i % 2 else "Графы", "level": (i % 4) + 1,
             "task_text": f"Задача {i}", "correct_answer": "1", "solution": "…"} for i in range(1, 17)]
    p = tmp_path / "bank.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
    bank_index.reset(); bank_index.load(path=p)
    yield recs
    bank_index.reset()


def _login(client, user):
    with client.session_transaction() as s:
        s["_user_id"] = str(user.id); s["_fresh"] = True


def test_pages_render_for_teacher(page_app, teacher_user):
    c = page_app.test_client(); _login(c, teacher_user)
    r = c.get("/teacher/worksheet/new")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for marker in ("btnGenerate", "fGrade", "fTopics", "fMode", "wsPreview", "btnAssign", "btnPdf"):
        assert marker in html
    r = c.get("/teacher/worksheets")
    assert r.status_code == 200 and "wlList" in r.get_data(as_text=True)


def test_pages_403_for_student(page_app, student_users):
    c = page_app.test_client(); _login(c, student_users[0])
    assert c.get("/teacher/worksheet/new").status_code == 403
    assert c.get("/teacher/worksheets").status_code == 403
    assert c.get("/api/teacher/worksheet/topics?grade=8").status_code == 403


def test_topics_endpoint(page_app, bank, teacher_user):
    c = page_app.test_client(); _login(c, teacher_user)
    d = c.get("/api/teacher/worksheet/topics?grade=8").get_json()
    names = {t["name"]: t["count"] for t in d["topics"]}
    assert names == {"Делимость": 8, "Графы": 8}
    assert c.get("/api/teacher/worksheet/topics?grade=3").get_json()["topics"] == []
