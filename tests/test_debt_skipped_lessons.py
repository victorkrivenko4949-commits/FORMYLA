# -*- coding: utf-8 -*-
"""Долг за пропущенные занятия (владелец, 05.11.2026).

Пропущенное занятие-практика раньше только попадало в плашку «В долгу»,
а задач по нему не было — кнопке «Открыть долг» нечего было показать.
Теперь за пропущенный день выдаются задачи из банка датой того дня,
и они идут в обычный блок долга — в том числе в выходной.

Run: pytest tests/test_debt_skipped_lessons.py -v
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.test_daily_debt_bank_path import (  # noqa: E402
    _dashboard_data, _make_assignments, _make_bank_tasks, _set_plan_anchor,
)


def _setup_user(uid, monkeypatch, lesson_day):
    from models import db, User
    import curator.session_plan as sp
    u = User(id=uid, email=f'skip{uid}@test.invalid', nickname=f'skip{uid}')
    db.session.add(u)
    db.session.commit()
    _make_assignments(u.id, ["s1", "s2", "s3", "s4", "s5", "s6", "s7"])
    _set_plan_anchor(u.id, lesson_day)
    _make_bank_tasks(count=6)
    monkeypatch.setattr(sp, '_pilot', lambda _uid: True)
    monkeypatch.setattr(sp, '_lessons', lambda _uid: [
        {'status': 'skipped', 'lesson_type': 'practice', 'assigned_date': lesson_day},
    ])
    return u


def test_skipped_practice_gets_debt_tasks(app, monkeypatch):
    from services.daily_debt import issue_tasks_for_skipped_lessons, get_debt_items
    yesterday = date.today() - timedelta(days=1)
    u = _setup_user(8901, monkeypatch, yesterday)

    assert issue_tasks_for_skipped_lessons(u.id) == 1
    # повторный заход — без новых выдач
    assert issue_tasks_for_skipped_lessons(u.id) == 0

    debt = get_debt_items(u.id)
    assert len(debt) == 5
    assert {d['issued_date'] for d in debt} == {yesterday.isoformat()}


def test_old_skipped_lesson_not_issued(app, monkeypatch):
    from services.daily_debt import issue_tasks_for_skipped_lessons, DEBT_TTL_DAYS
    old = date.today() - timedelta(days=DEBT_TTL_DAYS + 1)
    u = _setup_user(8902, monkeypatch, old)
    assert issue_tasks_for_skipped_lessons(u.id) == 0


def test_rest_day_page_shows_debt_for_skipped_lesson(app, client, monkeypatch):
    import daily_tasks.routes as r
    yesterday = date.today() - timedelta(days=1)
    u = _setup_user(8903, monkeypatch, yesterday)
    monkeypatch.setattr(r, '_session_plan_ctx', lambda _uid: {
        'active': True, 'today_rest': True, 'today_done': False,
        'next_lesson_day': 'Сб', 'plan': [], 'debts_count': 1,
        'debts': [{'lesson_label': 'практика', 'theme': 's1'}],
        'completed_lessons': 0, 'lesson_type': 'practice',
    })
    with client.session_transaction() as sess:
        sess['_user_id'] = str(u.id)

    data = _dashboard_data(client)
    assert data.get('status') == 'rest_day'
    assert data.get('debt') and data['debt']['total'] == 5
    html = client.get('/daily_tasks', follow_redirects=True).get_data(as_text=True)
    assert 'Открыть долг' in html
