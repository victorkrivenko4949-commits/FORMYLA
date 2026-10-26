# -*- coding: utf-8 -*-
"""Реальный Flask-маршрут /daily_tasks: план на 6 занятий и долги.

Проверяет не изолированный Jinja-блок, а НАСТОЯЩУЮ страницу дашборда
(маршрут, контекст, шаблон целиком) для пилота (uid=1 victor).

Run: pytest tests/test_session_plan_routes.py -v
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest


def _backdate(lesson_id: int, days: int = 1):
    from app import app
    from models import db
    from sqlalchemy import text
    with app.app_context():
        db.session.execute(text(
            "UPDATE curator_lessons SET assigned_date = :d WHERE id = :lid"),
            {'d': date.today() - timedelta(days=days), 'lid': lesson_id})
        db.session.commit()


@pytest.fixture()
def pilot_client():
    """Test client реального приложения, залогинен как uid=1 (пилот)."""
    from app import app
    from models import db, User

    with app.app_context():
        if not User.query.get(1):
            u = User(email='victor@test.local', nickname='victor')
            db.session.add(u)
            db.session.commit()
        # анкета «пройдена» — иначе before_request гоняет на /intake
        from models_curator import CuratorState
        import json as _json
        cs = CuratorState.query.filter_by(user_id=1).first()
        if cs is None:
            cs = CuratorState(user_id=1)
            db.session.add(cs)
        cs.grade = 9
        cs.prep_state = _json.dumps({'intake': {'completed': True}})
        db.session.commit()
        # чистим историю занятий тестового пользователя (локальная база)
        from curator.session_plan import ensure_tables
        ensure_tables()
        from sqlalchemy import text
        db.session.execute(text(
            "DELETE FROM curator_lessons WHERE user_id = 1"))
        db.session.commit()

    with app.test_client() as c:
        # dev_login работает только с localhost — test client как раз
        rv = c.get('/dev_login?uid=1')
        assert rv.status_code in (200, 302), (rv.status_code, rv.data[:200])
        yield c

    with app.app_context():
        from sqlalchemy import text
        from models import db
        db.session.execute(text(
            "DELETE FROM curator_lessons WHERE user_id = 1"))
        db.session.commit()


def test_dashboard_shows_six_lesson_plan(pilot_client):
    """Дашборд: полоса плана из 6 слотов, текущее выделено, CTA на месте."""
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200, rv.status_code
    html = rv.get_data(as_text=True)
    # карточка плана и заголовок
    assert 'План на 6 занятий' in html
    assert 'сдвигается каждый день' in html
    # первый слот — метод, текущий
    assert 'изучение метода' in html
    assert 'сейчас' in html
    # типы в полосе: метод, практики, пробник
    assert 'пробник' in html
    assert 'практика' in html
    # CTA текущего занятия
    assert 'К методу' in html
    # долгов пока нет — строка не показывается
    assert 'В долгу' not in html


def test_dashboard_today_done_and_debt(pilot_client):
    """Завершение → «выполнено, завтра»; пропуск дня → «В долгу: 1»."""
    from app import app
    from curator import session_plan

    # первый заход создаёт урок-метод (назначен сегодня)
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200

    with app.app_context():
        lesson = session_plan.current_lesson(1)
        assert lesson is not None and lesson['lesson_type'] == 'method'
        assert session_plan.complete_current_lesson(1, 'method') is True
        lesson_id = lesson['id']

    # рефреш в тот же день: день закрыт, следующее — завтра
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'Сегодняшнее занятие выполнено' in html
    assert 'завтра' in html

    # «наступает завтра»: вчерашний урок сделан, сегодня — новый (практика)
    _backdate(lesson_id, days=1)
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'В долгу' not in html          # пропусков не было
    assert 'практика' in html             # слот 2 — практика

    # сегодняшний урок НЕ сделан, день прошёл → долг
    with app.app_context():
        cur = session_plan.current_lesson(1)
        assert cur is not None
        cur_id = cur['id']
    _backdate(cur_id, days=1)
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'В долгу: 1' in html
    # план пошёл дальше — следующий слот (практика) текущий
    assert 'сейчас' in html
