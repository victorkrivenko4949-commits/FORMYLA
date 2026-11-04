# -*- coding: utf-8 -*-
"""ADMIN restore-practice-day: обратная операция к force-probnik-day.

Пробник убран из ротации (владелец, 03.11.2026): на 6-й позиции блока
всем Premium-пользователям выдаётся практика. Эндпоинт конвертирует
СЕГОДНЯШНЕЕ занятие-пробник обратно в практику с темой из ротации.

Run: pytest tests/test_restore_practice_day.py -v
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest


@pytest.fixture()
def admin_client():
    """Test client, залогинен как uid=1 (victor, is_admin=True)."""
    from app import app
    from models import db, User
    from models_curator import CuratorState

    with app.app_context():
        u = User.query.get(1)
        if not u:
            u = User(email='victor@test.local')
            db.session.add(u)
        u.nickname = 'victor'  # uid=1 — админ по определению is_admin
        db.session.commit()
        cs = CuratorState.query.filter_by(user_id=1).first()
        if cs is None:
            cs = CuratorState(user_id=1)
            db.session.add(cs)
        cs.grade = 9
        cs.prep_state = json.dumps({'intake': {'completed': True}})
        db.session.commit()
        from curator.session_plan import ensure_tables
        from sqlalchemy import text
        ensure_tables()
        db.session.execute(text('DELETE FROM curator_lessons WHERE user_id = 1'))
        # выбор дней пилота (user_schedule_days) может сделать сегодня
        # выходным для uid=1 — тогда занятие не создаётся и тест падает.
        # Активная пилотная подписка без выбора дней включает гейт
        # force_schedule_selection (редирект /daily_tasks -> /schedule).
        # Чистим и то и другое, чтобы тест не зависел от локальной БД.
        db.session.execute(text('DELETE FROM user_schedule_days WHERE user_id = 1'))
        db.session.execute(text("DELETE FROM subscriptions WHERE user_id = 1 "
                                "AND plan IN ('premium_intense', 'premium_calm')"))
        db.session.commit()

    with app.test_client() as c:
        rv = c.get('/dev_login?uid=1')
        assert rv.status_code in (200, 302)
        yield c

    with app.app_context():
        from sqlalchemy import text
        from models import db
        db.session.execute(text('DELETE FROM curator_lessons WHERE user_id = 1'))
        db.session.commit()


def _today_lesson(uid: int = 1):
    from app import app
    from curator.session_plan import _lessons
    with app.app_context():
        for l in reversed(_lessons(uid)):
            d = l.get('assigned_date')
            if hasattr(d, 'date'):
                d = d.date()
            if str(d)[:10] == str(date.today()):
                return l
    return None


def test_restore_practice_day_roundtrip(admin_client):
    """force-probnik-day → restore-practice-day: занятие снова практика."""
    # 1) синхронизируем расписание — создаётся сегодняшнее занятие
    rv = admin_client.get('/daily_tasks')
    assert rv.status_code == 200
    lesson = _today_lesson()
    assert lesson is not None, 'сегодняшнее занятие не создано'
    orig_type = lesson['lesson_type']
    assert orig_type == 'method', f'ожидали method (1-я позиция), {orig_type}'

    # 2) назначаем пробник (vsosh, 9 класс — реальный каталог)
    rv = admin_client.post('/curator/admin/force-probnik-day',
                           json={'olympiad_slug': 'vsosh'})
    assert rv.status_code == 200, rv.get_data(as_text=True)
    data = rv.get_json()
    assert data['success'] is True
    lesson = _today_lesson()
    assert lesson['lesson_type'] == 'probnik'
    assert lesson.get('probnik_code')

    # 3) возвращаем практику
    rv = admin_client.post('/curator/admin/restore-practice-day', json={})
    assert rv.status_code == 200, rv.get_data(as_text=True)
    data = rv.get_json()
    assert data['success'] is True
    assert data['lesson_id'] == lesson['id']
    assert data.get('theme'), 'тема практики не назначена'
    lesson = _today_lesson()
    assert lesson['lesson_type'] == 'practice'
    assert not lesson.get('probnik_code')
    assert not lesson.get('probnik_title')
    assert lesson.get('theme') == data['theme']

    # 4) повторный вызов: сегодня не пробник → 400
    rv = admin_client.post('/curator/admin/restore-practice-day', json={})
    assert rv.status_code == 400
    assert rv.get_json()['error'] == 'today is not a probnik lesson'


def test_restore_practice_day_no_lesson(admin_client):
    """Нет занятия сегодня → 404, ничего не ломаем."""
    from app import app
    from sqlalchemy import text
    from models import db
    with app.app_context():
        db.session.execute(text('DELETE FROM curator_lessons WHERE user_id = 1'))
        db.session.commit()
    rv = admin_client.post('/curator/admin/restore-practice-day', json={})
    assert rv.status_code == 404
    assert rv.get_json()['error'] == 'no lesson today'


def test_restore_practice_day_forbidden_for_non_admin():
    """Не-админ получает 403."""
    from app import app
    from models import db, User
    from models_curator import CuratorState
    import json as _json

    with app.app_context():
        u = db.session.query(User).filter(User.email == 'plain@test.local').first()
        if not u:
            u = User(email='plain@test.local')
            db.session.add(u)
            db.session.commit()
        plain_id = u.id
        cs = CuratorState.query.filter_by(user_id=u.id).first()
        if cs is None:
            cs = CuratorState(user_id=u.id)
            db.session.add(cs)
        cs.grade = 9
        cs.prep_state = _json.dumps({'intake': {'completed': True}})
        db.session.commit()

    with app.test_client() as c:
        rv = c.get('/dev_login?uid=%d' % plain_id)
        assert rv.status_code in (200, 302)
        rv = c.post('/curator/admin/restore-practice-day', json={})
        assert rv.status_code == 403
