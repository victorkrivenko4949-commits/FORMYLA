# -*- coding: utf-8 -*-
"""Воспроизведение вопроса владельца (01.11.2026): «куда делись эти 3 задачи?»
на карточке «Сегодня — день метода».

Сценарий: пилот (id=5, как Lavrik) в день метода без оплаченного доступа.
Карточка на /daily_tasks рендерится (задачи дня бесплатны), но 3 задачи
метода грузятся виджетом из /method_week/api/today — а этот раздел с 28.10
платный (FREE_TIER_V2). Проверяем: без Premium API отвечает 402, и вместо
задач виджет показывает заглушку paywall.
"""
import json

import pytest
from sqlalchemy import text


@pytest.fixture
def mw_app(app, monkeypatch):
    monkeypatch.setenv('PAYWALL_ENABLED', '1')
    monkeypatch.setenv('PAYWALL_START_DATE', '2026-10-01')
    monkeypatch.setenv('PAYWALL_MODE', 'rollout')
    monkeypatch.setenv('FREE_LIMITS_DISABLED', '1')
    from models import db
    from sqlalchemy import text
    db.create_all()
    pg = db.engine.dialect.name == 'postgresql'
    serial = 'SERIAL PRIMARY KEY' if pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    for ddl in (
        f"""CREATE TABLE IF NOT EXISTS usage_daily (
            id {serial}, user_id INTEGER NOT NULL,
            date TEXT NOT NULL, tasks_completed INTEGER DEFAULT 0,
            ai_explanations_used INTEGER DEFAULT 0, tokens_consumed INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0)""",
        f"""CREATE TABLE IF NOT EXISTS subscriptions (
            id {serial}, user_id INTEGER NOT NULL, plan TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active', started_at TIMESTAMP, expires_at TIMESTAMP,
            payment_method TEXT, payment_id TEXT, amount_rub INTEGER, is_trial INTEGER DEFAULT 0,
            is_beta_access INTEGER DEFAULT 1, created_at TIMESTAMP)""",
    ):
        db.session.execute(text(ddl))
    db.session.commit()
    from method_week.paywall import install_paywall
    from method_week import method_week_bp
    install_paywall(app)
    app.register_blueprint(method_week_bp)
    return app


def _mk_pilot_user(appl, uid=5):
    """Пилот id=5 (Lavrik): без подписок и без trial — бесплатник."""
    from models import db, User
    u = db.session.get(User, uid)
    if u is None:
        u = User(id=uid, email='lavrik@test.local', is_guest=False)
        db.session.add(u)
    db.session.commit()
    # анкета пройдена — иначе before_request гоняет на /intake
    from models_curator import CuratorState
    cs = CuratorState.query.filter_by(user_id=uid).first()
    if cs is None:
        cs = CuratorState(user_id=uid)
        db.session.add(cs)
    cs.grade = 9
    cs.prep_state = json.dumps({'intake': {'completed': True}})
    db.session.commit()
    # сегодняшний урок — метод
    from curator.session_plan import ensure_tables, _insert_lesson
    ensure_tables()
    db.session.execute(text("DELETE FROM curator_lessons WHERE user_id = :u"), {'u': uid})
    db.session.commit()
    _insert_lesson(uid, 1, 'method', status='completed')
    db.session.commit()
    return u


def _client(appl, user):
    c = appl.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id)
    return c


def test_method_day_card_without_premium(mw_app):
    """День метода у бесплатного пилота: карточка есть, но задачи метода
    за paywall — /method_week/api/today отвечает 402."""
    from services.pilot import is_pilot_user
    from curator.session_plan import is_method_day

    u = _mk_pilot_user(mw_app, uid=5)
    assert is_pilot_user(5) is True
    assert is_method_day(5) is True

    c = _client(mw_app, u)

    # 1) дашборд: карточка «день метода» + виджет 3 задач на месте
    rv = c.get('/daily_tasks/')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'Сегодня — день метода' in html
    assert 'ОБЯЗАТЕЛЬНО изучи метод' in html
    assert '<div id="mw-root" data-mw-only="tasks">' in html

    # 2) НО API задач метода — платное: 402, а не задачи
    rv2 = c.get('/method_week/api/today',
                headers={'Accept': 'application/json',
                         'Content-Type': 'application/json'})
    assert rv2.status_code == 402, (
        'без Premium виджет получает 402 — вместо 3 задач показывается '
        'заглушка paywall: %r' % (rv2.get_data(as_text=True)[:200],))
    body = rv2.get_json()
    assert body.get('error') == 'payment_required'
    assert 'недоступен в бесплатной версии' in body.get('message', '')
    assert body.get('upgrade_url')


def test_method_day_card_with_paid(mw_app):
    """Контрфакт: та же карточка при активной подписке пилота — API отвечает
    200 и создаёт набор задач метода (статус generating, без реального
    генератора)."""
    from models import db
    from sqlalchemy import text
    u = _mk_pilot_user(mw_app, uid=5)
    # активная пилотная подписка premium_intense (бета) = платный доступ
    db.session.execute(text(
        "INSERT INTO subscriptions (user_id, plan, status, started_at, expires_at, is_beta_access) "
        "VALUES (5, 'premium_intense', 'active', datetime('now'), datetime('now', '+7 days'), 1)"))
    db.session.commit()

    c = _client(mw_app, u)
    rv = c.get('/method_week/api/today',
               headers={'Accept': 'application/json',
                        'Content-Type': 'application/json'})
    assert rv.status_code == 200, rv.get_data(as_text=True)[:300]
    body = rv.get_json()
    assert body.get('status') in ('generating', 'ready', 'no_plan')


def test_method_day_card_with_trial(mw_app):
    """Пробный день (trial_until в будущем) тоже открывает 3 задачи метода."""
    from datetime import datetime, timedelta
    from models import db
    u = _mk_pilot_user(mw_app, uid=5)
    u.trial_until = datetime.utcnow() + timedelta(hours=23)
    db.session.commit()

    c = _client(mw_app, u)
    rv = c.get('/method_week/api/today',
               headers={'Accept': 'application/json',
                        'Content-Type': 'application/json'})
    assert rv.status_code == 200, rv.get_data(as_text=True)[:300]
    body = rv.get_json()
    assert body.get('status') in ('generating', 'ready', 'no_plan')


def test_widget_paywall_stub_wording():
    """Заглушка виджета в режиме «3 задачи»: Premium/пробный день показывают
    задачи, бесплатнику — сообщение и кнопка «Оформить» (владелец, 02.11.2026)."""
    import os
    js = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'method_week.js'),
              encoding='utf-8').read()
    assert "MODE === 'tasks'" in js
    assert 'Задачи по методу доступны только в Premium' in js
    assert 'Оформить Premium' in js
    # кэш-версия скрипта поднята во всех точках подключения
    for tpl, needle in (
        ('templates/daily_tasks/daily_tasks_dashboard.html', 'method_week.js?v=4'),
        ('templates/olympiad/method.html', 'method_week.js?v=4'),
        ('method_week/ui_inject.py', 'method_week.js?v=4'),
    ):
        path = os.path.join(os.path.dirname(__file__), '..', tpl)
        assert needle in open(path, encoding='utf-8').read(), tpl
