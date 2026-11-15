# -*- coding: utf-8 -*-
"""Тесты для исправления дня «-19 из 7» и постоянной доступности кнопки «Открыть долги»."""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _login(client, uid: int):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(uid)


def _extract_init_data(html: str) -> dict:
    m = re.search(
        r'<script[^>]+id=["\']dt-init-data["\'][^>]*>(.*?)</script>',
        html,
        re.S,
    )
    return json.loads(m.group(1)) if m else {}


def test_future_renewal_does_not_produce_negative_diag_day(app):
    """Активная подписка-продление в будущем не должна сбивать diag_day_num в минус."""
    from models import db, User, Subscription
    from services.schedule_days import save_user_days
    from curator.session_plan import (
        session_info,
        _premium_started_at,
        _pilot_variant,
    )
    from services.pilot import pilot_session_today
    from services.curator_chat import _subscription_started_at

    uid = 97101
    u = User(id=uid, email="fut1@test.invalid", nickname="fut1", preferred_grade=11)
    db.session.add(u)
    db.session.commit()

    now = datetime.utcnow()
    # Текущая активная подписка (началась 3 дня назад -> день 4 из 7)
    s_cur = Subscription(
        user_id=uid,
        plan="premium_calm",
        status="active",
        started_at=now - timedelta(days=3),
        expires_at=now + timedelta(days=27),
        is_beta_access=False,
        is_trial=False,
    )
    # Продление / подаренная подписка, которая стартует через 27 дней
    s_fut = Subscription(
        user_id=uid,
        plan="premium_calm",
        status="active",
        started_at=now + timedelta(days=27),
        expires_at=now + timedelta(days=57),
        is_beta_access=False,
        is_trial=False,
    )
    db.session.add_all([s_cur, s_fut])
    db.session.commit()

    today_wd = date.today().weekday()
    assert save_user_days(uid, [today_wd, (today_wd + 2) % 7, (today_wd + 4) % 7], "premium_calm") is True

    started = _premium_started_at(uid)
    assert started is not None and started.date() == (now - timedelta(days=3)).date()
    assert _pilot_variant(uid) == "premium_calm"

    info = session_info(uid)
    assert info["active"] is True
    assert info["diag_day_num"] == 4
    assert 1 <= info["diag_day_num"] <= 7

    ps = pilot_session_today(uid)
    assert ps["enabled"] is True
    assert ps["week"] == 1
    assert ps["session_type"] in ("diagnostic", "rest")

    chat_started = _subscription_started_at(uid)
    assert chat_started is not None and chat_started <= now + timedelta(seconds=5)


def test_only_future_subscription_never_returns_negative_diag_day(app):
    """Даже если в БД только подписка с started_at в будущем, diag_day_num не отрицателен."""
    from models import db, User, Subscription
    from curator.session_plan import session_info, _premium_started_at
    from services.pilot import pilot_session_today

    uid = 97102
    u = User(id=uid, email="fut2@test.invalid", nickname="fut2", preferred_grade=11)
    db.session.add(u)
    db.session.commit()

    now = datetime.utcnow()
    s_fut = Subscription(
        user_id=uid,
        plan="premium_calm",
        status="active",
        started_at=now + timedelta(days=20),
        expires_at=now + timedelta(days=50),
        is_beta_access=False,
        is_trial=False,
    )
    db.session.add(s_fut)
    db.session.commit()

    assert _premium_started_at(uid) is None
    info = session_info(uid)
    assert info.get("diag_day_num") is None or info["diag_day_num"] >= 1
    ps = pilot_session_today(uid)
    assert ps.get("week") is None or ps["week"] >= 1


def test_open_debt_button_always_rendered_even_without_debts(app, client, monkeypatch):
    """Кнопка «Открыть долги» рендерится всегда — при 0 долгов, в выходной, день метода."""
    import daily_tasks.routes as r
    from models import db, User
    from tests.test_daily_debt_bank_path import _make_bank_tasks

    uid = 97103
    u = User(id=uid, email="btn@test.invalid", nickname="btn", preferred_grade=11)
    db.session.add(u)
    db.session.commit()
    _make_bank_tasks(count=6)
    _login(client, uid)

    # 1) Обычный дашборд без долгов (ready) — кнопка есть, но JSON data['debt'] пуст
    resp = client.get("/daily_tasks", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="dt-debt-toggle"' in html
    assert "Открыть долги" in html
    assert "Активных долгов сейчас нет" in html
    assert not _extract_init_data(html).get("debt")

    # 2) Выходной день (rest_day) без долгов
    monkeypatch.setattr(
        r,
        "_session_plan_ctx",
        lambda _uid: {
            "active": True,
            "today_rest": True,
            "today_done": False,
            "next_lesson_day": "Ср",
            "plan": [],
            "debts_count": 0,
            "debts": [],
            "completed_lessons": 1,
            "lesson_type": "practice",
        },
    )
    html_rest = client.get("/daily_tasks", follow_redirects=True).get_data(as_text=True)
    assert _extract_init_data(html_rest).get("status") == "rest_day"
    assert 'id="dt-debt-toggle"' in html_rest
    assert "Открыть долги" in html_rest

    # 3) День метода (method_day) без долгов
    import curator.session_plan as sp
    monkeypatch.setattr(sp, "is_method_day", lambda _uid: True)
    monkeypatch.setattr(
        r,
        "_session_plan_ctx",
        lambda _uid: {
            "active": True,
            "today_rest": False,
            "today_done": False,
            "lesson_type": "method",
            "method_code": "M01",
            "method_name": "Метод инварианта",
            "cta_url": "/method/M01",
            "plan": [],
            "debts_count": 0,
            "debts": [],
            "completed_lessons": 1,
        },
    )
    html_method = client.get("/daily_tasks", follow_redirects=True).get_data(as_text=True)
    assert _extract_init_data(html_method).get("status") == "method_day"
    assert 'id="dt-debt-toggle"' in html_method
    assert "Открыть долги" in html_method


def test_skipped_practice_without_curator_plan_gets_formyla_bank_tasks(app, client, monkeypatch):
    """Если CuratorPlan отсутствует (plan_missing), пропущенная практика берёт задачи из FORMYLA_BANK.jsonl."""
    import curator.session_plan as sp
    import daily_tasks.routes as r
    from models import db, User
    from services.daily_debt import issue_tasks_for_skipped_lessons, get_debt_items

    uid = 97104
    u = User(id=uid, email="fb@test.invalid", nickname="fb", preferred_grade=11)
    db.session.add(u)
    db.session.commit()

    yesterday = date.today() - timedelta(days=1)
    monkeypatch.setattr(sp, "_pilot", lambda _uid: True)
    monkeypatch.setattr(
        sp,
        "_lessons",
        lambda _uid: [
            {
                "id": 1,
                "status": "skipped",
                "lesson_type": "practice",
                "assigned_date": yesterday,
                "theme": "Чётность",
            }
        ],
    )

    issued = issue_tasks_for_skipped_lessons(uid)
    assert issued == 1
    debt = get_debt_items(uid)
    assert len(debt) == 5
    assert {d["issued_date"] for d in debt} == {yesterday.isoformat()}

    monkeypatch.setattr(
        r,
        "_session_plan_ctx",
        lambda _uid: {
            "active": True,
            "today_rest": True,
            "today_done": False,
            "next_lesson_day": "Вт",
            "plan": [],
            "debts_count": 1,
            "debts": [
                {
                    "lesson_label": "практика",
                    "theme": "Чётность",
                    "assigned_date": yesterday.isoformat(),
                    "lesson_type": "practice",
                }
            ],
            "completed_lessons": 0,
            "lesson_type": "practice",
        },
    )
    _login(client, uid)
    html = client.get("/daily_tasks", follow_redirects=True).get_data(as_text=True)
    assert "Открыть долги: 5 задач" in html
    data = _extract_init_data(html)
    assert data.get("debt") and data["debt"]["total"] == 5


def test_skipped_method_visible_in_debt_block_and_closes_on_completion(app, client):
    """Пропущенный метод показывается со ссылкой в блоке долгов и закрывается при прохождении метод-сета."""
    from sqlalchemy import text
    from models import db, User, Subscription
    from services.schedule_days import save_user_days
    from curator.session_plan import session_info, maybe_complete_method, TABLE_NAME
    from method_week.models import MethodWeekSet, MethodWeekAnswer

    uid = 97105
    u = User(id=uid, email="mdebt@test.invalid", nickname="mdebt", preferred_grade=11)
    db.session.add(u)
    now = datetime.utcnow()
    db.session.add(
        Subscription(
            user_id=uid,
            plan="premium_calm",
            status="active",
            started_at=now - timedelta(days=10),
            expires_at=now + timedelta(days=20),
            is_beta_access=False,
            is_trial=False,
        )
    )
    db.session.commit()

    today_wd = date.today().weekday()
    save_user_days(uid, [today_wd, (today_wd + 2) % 7, (today_wd + 4) % 7], "premium_calm")
    session_info(uid)
    yesterday = date.today() - timedelta(days=1)
    # Делаем 1 урок пропущенным методом (M01) за вчера
    db.session.execute(
        text(
            f"UPDATE {TABLE_NAME} SET status = 'skipped', lesson_type = 'method', "
            f"method_code = 'M01', method_name = 'Инвариант', assigned_date = :y "
            f"WHERE user_id = :u AND seq = 1"
        ),
        {"y": yesterday, "u": uid},
    )
    db.session.commit()

    info = session_info(uid)
    assert info["debts_count"] >= 1
    m_debts = [d for d in info["debts"] if d.get("lesson_type") == "method"]
    assert m_debts and "/methods/M01" in (m_debts[0].get("cta_url") or "")

    _login(client, uid)
    html = client.get("/daily_tasks", follow_redirects=True).get_data(as_text=True)
    assert "/methods/M01" in html
    assert "Изучить метод" in html

    # Закрываем метод-сет по M01 -> пропущенный урок должен стать completed
    mw = MethodWeekSet(
        user_id=uid,
        week_start=date.today() - timedelta(days=date.today().weekday() + 7),
        grade=11,
        level="base",
        method_code="M01",
        method_name="Инвариант",
        status="ready",
        tasks_json=json.dumps([{"position": 1, "text": "Задача", "answer": "42"}]),
    )
    db.session.add(mw)
    db.session.flush()
    db.session.add(
        MethodWeekAnswer(
            set_id=mw.id,
            user_id=uid,
            position=1,
            user_answer="42",
            is_correct=True,
        )
    )
    db.session.commit()

    assert maybe_complete_method(uid) is True
    row = db.session.execute(
        text(f"SELECT status FROM {TABLE_NAME} WHERE user_id = :u AND seq = 1"),
        {"u": uid},
    ).fetchone()
    assert row[0] == "completed"


def test_submit_ai_debt_clears_debt_and_closes_skipped_practice(app, client, monkeypatch):
    """Ответ через /daily_tasks/<id>/submit_ai снимает debt_status и закрывает пропущенную практику."""
    from sqlalchemy import text
    import services.solution_check_pipeline as scp
    from models import db, User, Subscription
    from services.schedule_days import save_user_days
    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    from curator.session_plan import session_info, TABLE_NAME

    uid = 97106
    u = User(id=uid, email="subai@test.invalid", nickname="subai", preferred_grade=11)
    db.session.add(u)
    now = datetime.utcnow()
    db.session.add(
        Subscription(
            user_id=uid,
            plan="premium_calm",
            status="active",
            started_at=now - timedelta(days=10),
            expires_at=now + timedelta(days=20),
            is_beta_access=False,
            is_trial=False,
        )
    )
    db.session.commit()

    today_wd = date.today().weekday()
    save_user_days(uid, [today_wd, (today_wd + 2) % 7, (today_wd + 4) % 7], "premium_calm")
    session_info(uid)
    yesterday = date.today() - timedelta(days=1)
    db.session.execute(
        text(
            f"UPDATE {TABLE_NAME} SET status = 'skipped', lesson_type = 'practice', "
            f"assigned_date = :y WHERE user_id = :u AND seq = 1"
        ),
        {"y": yesterday, "u": uid},
    )
    db.session.commit()

    ds = DailyTaskSet(
        user_id=uid,
        target_date=yesterday,
        class_level=11,
        status="ready",
        triggered_by="skipped_lesson_debt",
    )
    db.session.add(ds)
    db.session.flush()
    item = DailyTaskItem(
        daily_set_id=ds.id,
        position=1,
        topic="Чётность",
        difficulty_level=2,
        task_text="Найдите сумму.",
        correct_answer="10",
        solution="5+5=10",
        status="ready",
        debt_status="active",
        debt_until=date.today() + timedelta(days=6),
    )
    db.session.add(item)
    db.session.commit()

    monkeypatch.setattr(
        scp,
        "check_solution",
        lambda **kw: {"is_correct": True, "score": 1.0, "feedback": "Верно!"},
    )
    _login(client, uid)

    resp = client.post(
        f"/daily_tasks/{item.id}/submit_ai",
        json={
            "user_answer": "10",
            "user_solution": "Складываем 5 и 5, получаем 10, всё верно.",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "success"
    assert body["is_correct"] is True

    db.session.refresh(item)
    assert item.debt_status is None
    assert item.debt_until is None

    row = db.session.execute(
        text(f"SELECT status FROM {TABLE_NAME} WHERE user_id = :u AND seq = 1"),
        {"u": uid},
    ).fetchone()
    assert row[0] == "completed"
