# -*- coding: utf-8 -*-
"""TG_TRIAL_WEEK — «Неделя Premium за подписку на Telegram-канал».

Запуск: pytest tests/test_tg_trial_week.py -q
Telegram Bot API замокан — сеть не нужна.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text


@pytest.fixture
def tg_app(app, monkeypatch):
    from models import db
    import models_tg_trial  # noqa: F401
    db.create_all()
    db.session.execute(text("""CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, plan TEXT NOT NULL DEFAULT 'free',
        status TEXT NOT NULL DEFAULT 'active', started_at TIMESTAMP, expires_at TIMESTAMP,
        payment_method TEXT, payment_id TEXT, amount_rub INTEGER, is_trial INTEGER DEFAULT 0,
        is_beta_access INTEGER DEFAULT 1, created_at TIMESTAMP)"""))
    db.session.commit()
    # id 1/5 — пилотные аккаунты (у них Premium и так); начинаем id с 100
    db.session.execute(text("INSERT INTO users (id, email, is_guest) VALUES (99, 'seed@x.ru', 0)"))
    db.session.commit()
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'test-token')
    monkeypatch.setenv('TG_TRIAL_CHANNEL', 'FormylaMaths')
    import services.subscription as sub
    monkeypatch.setattr(sub, '_service_instance', None)
    from services import tg_trial
    members = set()
    monkeypatch.setattr(tg_trial, 'check_membership', lambda tg_id: str(tg_id) in members)
    from routes.tg_trial import tg_trial_bp
    if 'tg_trial' not in app.blueprints:
        app.register_blueprint(tg_trial_bp)
    app.tg_members = members
    return app


def _user(email, tg_id=None, role='student'):
    from models import db, User
    u = User(email=email, is_guest=False, telegram_id=tg_id)
    try:
        u.role = role
    except Exception:
        pass
    db.session.add(u)
    db.session.commit()
    return u


def _active_subs(uid):
    from models import db
    return db.session.execute(text(
        "SELECT plan, expires_at, is_trial FROM subscriptions WHERE user_id=:u AND status='active'"),
        {'u': uid}).fetchall()


def test_week_granted_exactly_7_days(tg_app):
    from services import tg_trial
    u = _user('a@x.ru', tg_id='111')
    tg_app.tg_members.add('111')
    assert tg_trial.get_state(u)['state'] == 'available'
    before = datetime.utcnow()
    res = tg_trial.claim_week(u)
    exp = datetime.fromisoformat(res['expires_at'])
    assert timedelta(days=7) - timedelta(seconds=5) < exp - before <= timedelta(days=7, seconds=5)
    subs = _active_subs(u.id)
    assert len(subs) == 1 and subs[0][0] == 'premium_intense' and int(subs[0][2]) == 1
    assert tg_trial.get_state(u)['state'] == 'active'
    from services.pilot import has_premium_access
    assert has_premium_access(u)


def test_not_subscribed_refused(tg_app):
    from services import tg_trial
    u = _user('b@x.ru', tg_id='222')
    with pytest.raises(tg_trial.TgTrialError) as e:
        tg_trial.claim_week(u)
    assert e.value.code == 'not_member'
    assert _active_subs(u.id) == []


def test_only_once_per_account(tg_app):
    from services import tg_trial
    u = _user('c@x.ru', tg_id='333')
    tg_app.tg_members.add('333')
    tg_trial.claim_week(u)
    with pytest.raises(tg_trial.TgTrialError) as e:
        tg_trial.claim_week(u)
    assert e.value.code == 'already_active'


def test_only_once_per_telegram(tg_app):
    """Отвязал Telegram, привязал к новому аккаунту — вторую неделю не дадим."""
    from models import db
    from services import tg_trial
    u1 = _user('d1@x.ru', tg_id='444')
    tg_app.tg_members.add('444')
    tg_trial.claim_week(u1)
    u1.telegram_id = None
    db.session.commit()
    u2 = _user('d2@x.ru', tg_id='444')
    with pytest.raises(tg_trial.TgTrialError) as e:
        tg_trial.claim_week(u2)
    assert e.value.code == 'tg_used'


def test_need_telegram_linked(tg_app):
    from services import tg_trial
    u = _user('e@x.ru')
    st = tg_trial.get_state(u)
    assert st['state'] == 'available' and st['tg_linked'] is False
    with pytest.raises(tg_trial.TgTrialError) as e:
        tg_trial.claim_week(u)
    assert e.value.code == 'need_tg'


def test_paid_premium_not_needed(tg_app):
    from models import db
    from services import tg_trial
    u = _user('f@x.ru', tg_id='555')
    db.session.execute(text(
        "INSERT INTO subscriptions (user_id, plan, status, started_at, expires_at, payment_id, is_trial, is_beta_access)"
        " VALUES (:u, 'premium_intense', 'active', :s, :e, 'pay_1', 0, 0)"),
        {'u': u.id, 's': datetime.utcnow() - timedelta(days=1), 'e': datetime.utcnow() + timedelta(days=20)})
    db.session.commit()
    assert tg_trial.get_state(u)['state'] == 'premium'


def test_week_replaces_active_trial_day(tg_app):
    from models import db
    from services import tg_trial
    u = _user('g@x.ru', tg_id='666')
    tg_app.tg_members.add('666')
    db.session.execute(text(
        "INSERT INTO subscriptions (user_id, plan, status, started_at, expires_at, is_trial, is_beta_access)"
        " VALUES (:u, 'premium_intense', 'active', :s, :e, 1, 1)"),
        {'u': u.id, 's': datetime.utcnow(), 'e': datetime.utcnow() + timedelta(hours=20)})
    db.session.commit()
    assert tg_trial.get_state(u)['state'] == 'available'
    tg_trial.claim_week(u)
    subs = _active_subs(u.id)
    assert len(subs) == 1  # пробный день погашен, осталась неделя
    exp = subs[0][1]
    exp = exp if isinstance(exp, datetime) else datetime.fromisoformat(str(exp))
    assert exp - datetime.utcnow() > timedelta(days=6, hours=23)


def test_parent_hidden(tg_app):
    from services import tg_trial
    u = _user('h@x.ru', tg_id='777', role='parent')
    if getattr(u, 'role', 'student') != 'parent':
        pytest.skip('в модели нет роли')
    assert tg_trial.get_state(u)['state'] == 'hidden'


def test_claim_endpoint_with_csrf(tg_app):
    u = _user('i@x.ru', tg_id='888')
    tg_app.tg_members.add('888')
    c = tg_app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u.id)
        s['_fresh'] = True
        s['_csrf_token'] = 'tok'
    r = c.post('/api/tg-trial/claim', json={})
    assert r.status_code == 400 and r.get_json()['code'] == 'csrf'
    r = c.post('/api/tg-trial/claim', json={}, headers={'X-CSRF-Token': 'tok'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['ok'] is True
    r = c.get('/api/tg-trial/status')
    assert r.get_json()['state'] == 'active'
