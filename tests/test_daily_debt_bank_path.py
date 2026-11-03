# -*- coding: utf-8 -*-
"""P4 DEBT на банк-ветке выдачи задач дня.

Регрессия (03.11.2026): задачи дня по умолчанию выдаются из
daily_task_bank, а эта ветка рендерила дашборд БЕЗ data['debt'] —
блок «Открыть долг: N задач» (нерешённые задачи прошлых дней,
на которые ученик не ответил) пропал со страницы. Тест гоняет
НАСТОЯЩИЙ маршрут /daily_tasks для непилота на банк-ветке.

Run: pytest tests/test_daily_debt_bank_path.py -v
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DT_INIT_RE = re.compile(
    r'<script id="dt-init-data" type="application/json">(.*?)</script>', re.S,
)


def _dashboard_data(client) -> dict:
    """GET /daily_tasks → разобранный dt-init-data JSON страницы."""
    rv = client.get('/daily_tasks', follow_redirects=True)
    assert rv.status_code == 200, rv.status_code
    html = rv.get_data(as_text=True)
    m = _DT_INIT_RE.search(html)
    assert m, 'dt-init-data не найден на странице'
    return json.loads(m.group(1))


def _make_assignments(user_id, subtopics, month=1):
    from models import db, UserSubtopicAssignment
    for pos, sub in enumerate(subtopics, 1):
        db.session.add(UserSubtopicAssignment(
            user_id=user_id,
            subtopic=sub,
            month_number=month,
            position=pos,
        ))
    db.session.commit()


def _set_plan_anchor(user_id, anchor_date, grade=9):
    from models import db
    from models_curator import CuratorState
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if cs is None:
        cs = CuratorState(user_id=user_id, grade=grade)
        db.session.add(cs)
    cs.grade = grade
    cs.prep_plan = {
        "version": 1,
        "anchor_date": anchor_date.isoformat(),
        "subtopics_per_month": 7,
        "grade": grade,
        "months": [{"index": 1, "subtopics": [
            "s1", "s2", "s3", "s4", "s5", "s6", "s7",
        ]}],
    }
    db.session.commit()


def _make_bank_tasks(subtopic="s1", count=6, level=3, section="algebra"):
    """Создать count задач в daily_task_bank, вернуть список id."""
    from models import db, DailyTaskBank
    ids = []
    for i in range(count):
        t = DailyTaskBank(
            subtopic=subtopic,
            section=section,
            level=level,
            statement=f"[TEST] Bank debt task #{i}",
            answer=f"answer_{i}",
            solution=f"solution_{i}",
            source_model="deepseek",
            position=i + 1,
        )
        db.session.add(t)
        db.session.flush()
        ids.append(t.id)
    db.session.commit()
    return ids


def _login_nonpilot(client, user_id: int) -> None:
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)


def test_bank_path_dashboard_shows_debt_block(app, client):
    """Банк-ветка /daily_tasks: старая неотвеченная задача — в блоке долга."""
    from models import db, BankIssue, User

    # непилотный id: пилотный id=1 уходит в ветку «день метода» до банка
    u = User(id=8801, email='debt_bank@test.invalid', nickname='debt_bank')
    db.session.add(u)
    db.session.commit()
    _login_nonpilot(client, u.id)

    _make_assignments(u.id, ["s1", "s2", "s3", "s4", "s5", "s6", "s7"])
    _set_plan_anchor(u.id, date.today())
    task_ids = _make_bank_tasks(count=6)

    # вчерашняя выдача без ответа — нерешённый долг из банка
    db.session.add(BankIssue(
        user_id=u.id,
        task_id=task_ids[0],
        subtopic="s1",
        level=3,
        issued_date=date.today() - timedelta(days=1),
    ))
    db.session.commit()

    data = _dashboard_data(client)

    # выдача прошла именно через банк: 5 свежих задач сего дня
    assert data.get('status') == 'ready'
    assert len(data.get('items') or []) == 5
    # долг на месте: одна просроченная неотвеченная задача
    debt = data.get('debt')
    assert debt, 'data["debt"] отсутствует на банк-ветке — блок долга пропал'
    assert debt['total'] == 1
    dates = [g['date'] for g in debt['by_date']]
    assert dates == [(date.today() - timedelta(days=1)).isoformat()]
    assert debt['by_date'][0]['tasks'][0]['id'] == task_ids[0]
    assert debt['by_date'][0]['tasks'][0]['days_left'] is not None


def test_bank_path_debt_disappears_when_answered(app, client):
    """Ответленная вчера задача в долг не попадает."""
    from models import db, BankIssue, User

    u = User(id=8803, email='debt_bank2@test.invalid', nickname='debt_bank2')
    db.session.add(u)
    db.session.commit()
    _login_nonpilot(client, u.id)

    _make_assignments(u.id, ["s1", "s2", "s3", "s4", "s5", "s6", "s7"])
    _set_plan_anchor(u.id, date.today())
    task_ids = _make_bank_tasks(count=6)

    db.session.add(BankIssue(
        user_id=u.id,
        task_id=task_ids[0],
        subtopic="s1",
        level=3,
        issued_date=date.today() - timedelta(days=1),
        user_answer="answer_0",          # отвечена — долга нет
        is_correct=True,
    ))
    db.session.commit()

    data = _dashboard_data(client)
    assert data.get('status') == 'ready'
    assert not data.get('debt'), 'ответленная задача не должна попадать в долг'
