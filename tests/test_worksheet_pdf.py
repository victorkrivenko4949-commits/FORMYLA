# -*- coding: utf-8 -*-
"""Спринт 1, этап 5: PDF листка — владелец/ученик/посторонний, with_solutions, LaTeX-fallback."""
import json
from datetime import datetime, timedelta

import pytest

from models import db, T10Group, T10GroupMember
from teacher import teacher_bp
from teacher.worksheets import bank_index
from teacher.worksheets.models import Worksheet, WorksheetTask, WorksheetAssignment
from teacher.worksheets.pdf import latex_to_text

pytest.importorskip("reportlab")


@pytest.fixture
def pdf_app(app):
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
    recs = [{"position": i, "grade": 8, "topic": "Делимость", "level": (i % 4) + 1, "olympiad": "ВсОШ", "year": 2023,
             "number": i, "task_text": f"Задача {i}: докажите, что $\\frac{{n^2+1}}{{2}} \\cdot x^{{10}} \\le 5$.",
             "correct_answer": "$x=\\frac{3}{4}$", "solution": "Решение $a^2+b^2=c^2$."} for i in range(1, 9)]
    p = tmp_path / "bank.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
    bank_index.reset(); bank_index.load(path=p)
    yield recs
    bank_index.reset()


@pytest.fixture
def worksheet(pdf_app, teacher_user, student_users):
    with pdf_app.app_context():
        g = T10Group(name="PDF group", teacher_id=teacher_user.id, invite_code="PDF001")
        db.session.add(g); db.session.flush()
        db.session.add(T10GroupMember(group_id=g.id, user_id=student_users[0].id, role="student"))
        ws = Worksheet(teacher_id=teacher_user.id, group_id=g.id, title="Листок PDF", grade=8, status="assigned")
        for i in range(1, 9):
            ws.tasks.append(WorksheetTask(task_id=i, position=i, target_level=(i % 4) + 1))
        db.session.add(ws); db.session.flush()
        db.session.add(WorksheetAssignment(worksheet_id=ws.id, student_id=student_users[0].id,
                                           due_at=datetime.utcnow() + timedelta(days=3)))
        db.session.commit()
        return ws.id


def _login(client, user):
    with client.session_transaction() as s:
        s["_user_id"] = str(user.id); s["_fresh"] = True


def test_latex_fallback_readable():
    text, had = latex_to_text(r"Пусть $\frac{n^2+1}{2} \cdot x^{10} \le \sqrt{a_1}$ и $\angle ABC = 90^\circ$.")
    assert had
    assert "(n²+1)/(2)" in text and "x¹⁰" in text and "≤" in text and "√a₁" in text and "∠ ABC = 90°" in text
    assert "\\" not in text
    assert latex_to_text("без формул") == ("без формул", False)


def test_owner_gets_pdf_and_solutions(pdf_app, bank, teacher_user, worksheet):
    c = pdf_app.test_client(); _login(c, teacher_user)
    r = c.get(f"/teacher/worksheet/{worksheet}.pdf")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data[:5] == b"%PDF-"
    r2 = c.get(f"/teacher/worksheet/{worksheet}.pdf?with_solutions=1")
    assert r2.status_code == 200 and r2.data[:5] == b"%PDF-"


def test_student_plain_ok_solutions_403(pdf_app, bank, student_users, worksheet):
    c = pdf_app.test_client(); _login(c, student_users[0])
    assert c.get(f"/teacher/worksheet/{worksheet}.pdf").status_code == 200
    assert c.get(f"/teacher/worksheet/{worksheet}.pdf?with_solutions=1").status_code == 403


def test_stranger_403_and_missing_404(pdf_app, bank, student_users, worksheet):
    c = pdf_app.test_client(); _login(c, student_users[-1] if len(student_users) > 1 else student_users[0])
    if len(student_users) > 1:
        assert c.get(f"/teacher/worksheet/{worksheet}.pdf").status_code == 403
    assert c.get("/teacher/worksheet/999999.pdf").status_code == 404
