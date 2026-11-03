# -*- coding: utf-8 -*-
"""OPEN_SALES_V1 (03.11.2026): покупка Premium открыта всем.

PILOT_OPEN_SALES=True в services/pilot.py — чекаут и страница возврата
платежа доступны любому зарегистрированному (не только пилотному списку).
Полный Premium-продукт (поток занятий, куратор-чат) следует за активной
подпиской на пилотный тариф: has_premium_access.

Run: pytest tests/test_open_sales.py -v
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest

from models import Subscription  # noqa: E402


@pytest.fixture()
def plain_student(app):
    """Обычный студент: НЕ в пилотном списке, без подписки, анкета пройдена.

    id=99001: явный id вне PILOT_USER_IDS (в чистой tmp-базе первый
    пользователь получил бы id=1 — а это пилот).
    """
    from models import db, User
    from models_curator import CuratorState
    import json
    user = User(id=99001, email='opensales_student@example.invalid',
                nickname='opensales_student_99001')
    db.session.add(user)
    db.session.commit()
    cs = CuratorState(user_id=user.id)
    cs.prep_state = json.dumps({'intake': {'completed': True}})
    db.session.add(cs)
    db.session.commit()
    return user


@pytest.fixture()
def subscriber(app, plain_student):
    """Обычный студент (не пилот) с активной подпиской premium_calm."""
    from models import db, Subscription
    db.session.add(Subscription(
        user_id=plain_student.id, plan='premium_calm', status='active',
        started_at=datetime.utcnow() - timedelta(days=1),
        expires_at=datetime.utcnow() + timedelta(days=29)))
    db.session.commit()
    return plain_student


def _login(client, user_id: int):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)


# ── Покупка ──────────────────────────────────────────────────────────────

def test_checkout_open_to_all(app, client, plain_student):
    """Чекаут открыт обычному (не пилотному) аккаунту — не 404."""
    _login(client, plain_student.id)
    rv = client.get('/payments/premium/checkout?plan=premium_intense')
    assert rv.status_code == 200, (
        f'чекаут должен быть открыт всем, получен {rv.status_code}')
    assert 'Работяга' in rv.get_data(as_text=True)


def test_checkout_closed_when_flag_off(app, client, plain_student, monkeypatch):
    """PILOT_OPEN_SALES=False возвращает ограничение «до старта» — 404."""
    import services.pilot as pilot_mod
    monkeypatch.setattr(pilot_mod, 'PILOT_OPEN_SALES', False)
    _login(client, plain_student.id)
    rv = client.get('/payments/premium/checkout?plan=premium_intense')
    assert rv.status_code == 404, 'при закрытой продаже — 404, как до старта'


def test_pilot_checkout_still_works(app, monkeypatch):
    """Пилотному аккаунту чекаут по-прежнему доступен при любом флаге.

    Проверяем через реальное приложение (в conftest-приложении маршрут
    /payments/premium/checkout не зарегистрирован, а ensure_tables()
    автопродления кэшируется глобально на первую БД).
    """
    from app import app as real_app
    from models import db as real_db, User
    from datetime import datetime, timedelta
    from models_curator import CuratorState
    import json
    import services.pilot as pilot_mod
    with real_app.app_context():
        email = f'opensales_pilot_{datetime.utcnow().timestamp():.0f}@example.invalid'
        u = User(email=email, nickname=f"osp_{datetime.utcnow().timestamp():.0f}")
        real_db.session.add(u)
        real_db.session.commit()
        # без активной подписки: проверяем именно страницу покупки,
        # а не ветку «Premium уже активен»
        cs = CuratorState(user_id=u.id)
        cs.prep_state = json.dumps({'intake': {'completed': True}})
        real_db.session.add(cs)
        real_db.session.commit()
        # выбираем дни сразу — иначе гейт выбора дней уведёт на /schedule
        from services.schedule_days import save_user_days
        save_user_days(u.id, [0, 1, 2, 3, 4, 5], 'premium_intense')
        uid = u.id
    monkeypatch.setattr(pilot_mod, 'PILOT_USER_IDS', (uid,))
    c = real_app.test_client()
    _login(c, uid)
    rv = c.get('/payments/premium/checkout?plan=premium_calm')
    assert rv.status_code == 200, (
        f'пилоту чекаут должен быть доступен, получен {rv.status_code}')
    assert 'Спокойный' in rv.get_data(as_text=True)


# ── Продукт следует за подпиской ─────────────────────────────────────────

def test_has_premium_access_for_subscriber(app, subscriber):
    """Активная подписка даёт полный доступ даже без пилотного списка."""
    from services.pilot import has_premium_access
    assert has_premium_access(subscriber) is True
    assert has_premium_access(subscriber.id) is True


def test_no_access_for_plain_free_user(app, plain_student):
    """Без подписки и без пилотного списка — доступа нет."""
    from services.pilot import has_premium_access
    assert has_premium_access(plain_student) is False
    assert has_premium_access(plain_student.id) is False


def test_session_plan_active_for_subscriber(app, subscriber):
    """Поток занятий (полоса недели) включается у купившего тариф."""
    from curator.session_plan import session_info
    info = session_info(subscriber.id)
    assert info.get('active') is True, (
        'владелец тарифа должен получить поток занятий')
    assert info.get('lessons_per_week') == 3  # premium_calm


def test_curator_chat_open_for_subscriber(app, client, subscriber):
    """Куратор-чат доступен купившему тариф (раньше — только пилотам)."""
    _login(client, subscriber.id)
    rv = client.get('/curator')
    assert rv.status_code == 200, (
        f'куратор-чат должен быть открыт подписчику, получен {rv.status_code}')


def test_curator_chat_closed_for_free_user(app, client, plain_student):
    """Без подписки куратор-чат по-прежнему закрыт (404)."""
    _login(client, plain_student.id)
    rv = client.get('/curator')
    assert rv.status_code == 404


# ── Страница тарифов ─────────────────────────────────────────────────────

def test_subscribe_shows_buy_buttons_to_all():
    """Кнопки «Выбрать тариф» видны всем при открытой продаже.

    Через реальное приложение: в conftest-приложении /subscribe — заглушка.
    """
    from app import app as real_app
    from models import db as real_db, User
    from datetime import datetime
    import json
    from models_curator import CuratorState
    with real_app.app_context():
        email = f'opensales_sub_{datetime.utcnow().timestamp():.0f}@example.invalid'
        u = User(email=email, nickname=f"oss_{datetime.utcnow().timestamp():.0f}")
        real_db.session.add(u)
        real_db.session.commit()
        cs = CuratorState(user_id=u.id)
        cs.prep_state = json.dumps({'intake': {'completed': True}})
        real_db.session.add(cs)
        real_db.session.commit()
        uid = u.id
    c = real_app.test_client()
    _login(c, uid)
    rv = c.get('/subscribe')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert '/payments/premium/checkout?plan=premium_intense' in html, (
        'кнопка покупки «Работяги» должна быть видна не-пилоту')
    assert '/payments/premium/checkout?plan=premium_calm' in html, (
        'кнопка покупки «Спокойного» должна быть видна не-пилоту')
