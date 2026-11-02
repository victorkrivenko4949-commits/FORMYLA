# -*- coding: utf-8 -*-
"""PARENT_TEACHER_NO_BUY (02.11.2026) — родитель и учитель НЕ покупают Premium.

Роль берётся из первого вопроса анкеты (User.role). Правило:
  * родитель/учитель не может оформить Premium-пилот вообще — ни себе,
    ни подарочно для ребёнка (подарочный поток PREMIUM_GIFT_V1 закрыт);
  * checkout для него — редирект на /subscribe (там показывается
    «Оформите это в аккаунте ребёнка»);
  * create — 403 с этим же сообщением;
  * пробный день (/api/subscribe/trial) — тоже 403;
  * ученик (роль student, пилотный id) покупает как раньше.

Запуск: pytest tests/test_premium_gift.py -q
"""
import pytest


@pytest.fixture
def gift_app(app, monkeypatch):
    """Тестовое приложение с premium_pay и таблицами платежей/подписок."""
    monkeypatch.delenv('YOOKASSA_SHOP_ID', raising=False)
    monkeypatch.delenv('YOOKASSA_SECRET_KEY', raising=False)

    from routes.premium_pay import install_premium_pay
    from models import db
    from sqlalchemy import text

    install_premium_pay(app)
    db.create_all()

    # Таблицы, которые создаёт _ensure_tables (с колонкой beneficiary_user_id)
    with db.engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS yookassa_config (
                config_key VARCHAR(64) PRIMARY KEY,
                config_value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS yookassa_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id VARCHAR(64) UNIQUE NOT NULL,
                payment_id VARCHAR(128),
                user_id INTEGER NOT NULL,
                item_code VARCHAR(64) NOT NULL DEFAULT 'diamond_badge',
                amount_rub NUMERIC(10, 2) NOT NULL DEFAULT 10.00,
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                confirmation_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                beneficiary_user_id INTEGER
            )"""))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan TEXT NOT NULL DEFAULT 'free',
                status TEXT NOT NULL DEFAULT 'active',
                started_at TIMESTAMP, expires_at TIMESTAMP,
                payment_method TEXT, payment_id TEXT,
                amount_rub INTEGER, is_trial INTEGER DEFAULT 0,
                is_beta_access INTEGER DEFAULT 1, created_at TIMESTAMP
            )"""))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sub_user ON subscriptions(user_id)"))
        # Таблицы автопродления (ensure_tables кэширует флаг на уровне модуля,
        # поэтому создаём явно для каждой тестовой БД)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS premium_auto_renewals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                plan VARCHAR(64) NOT NULL,
                price_rub NUMERIC(10, 2) NOT NULL,
                payment_method_id VARCHAR(128),
                method_label VARCHAR(64),
                enabled INTEGER NOT NULL DEFAULT 1,
                next_charge_at TIMESTAMP,
                fail_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS premium_renewal_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                renewal_id INTEGER NOT NULL,
                period_start TIMESTAMP NOT NULL,
                period_end TIMESTAMP NOT NULL,
                order_id VARCHAR(64) UNIQUE NOT NULL,
                payment_id VARCHAR(128),
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (renewal_id, period_start)
            )"""))
    return app


def _make_user(email, nickname, role='student', uid=None):
    """Пользователь с ЯВНЫМ id: id=1/5/7452 — пилотные (services/pilot.py)."""
    from models import db, User
    if uid is None:
        # выбираем первый свободный id вне пилотных
        taken = {r[0] for r in db.session.execute(
            __import__('sqlalchemy').text('SELECT id FROM users')).fetchall()}
        uid = 10
        while uid in taken or uid in (1, 5, 7452):
            uid += 1
    u = User(id=uid, email=email, nickname=nickname, role=role, is_guest=False)
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, user):
    with client.session_transaction() as s:
        s['_user_id'] = str(user.id)


def _plan(user_id):
    from services.subscription import get_subscription_service
    return get_subscription_service().get_user_plan(user_id)


# ─────────────────────────── новое правило ────────────────────────────────

def test_parent_cannot_buy_for_child(gift_app):
    """Родитель (роль из анкеты) не покупает Premium даже для ребёнка."""
    from models import db, ParentChildLink

    parent = _make_user('gift_parent@example.invalid', 'gift_parent', role='parent')
    child = _make_user('gift_child@example.invalid', 'gift_child', role='student')
    db.session.add(ParentChildLink(
        parent_id=parent.id, child_id=child.id, status='accepted'))
    db.session.commit()

    client = gift_app.test_client()
    _login(client, parent)

    # Checkout — редирект на /subscribe (там сообщение про аккаунт ребёнка)
    resp = client.get(f'/payments/premium/checkout?plan=premium_intense&for_user={child.id}')
    assert resp.status_code == 302
    assert '/subscribe' in resp.headers['Location']

    # Создание платежа — 403 с сообщением, заказа не создаётся
    resp = client.post('/payments/premium/create', json={
        'plan': 'premium_intense', 'for_user': child.id,
    })
    assert resp.status_code == 403
    data = resp.get_json()
    assert 'аккаунте ребёнка' in data.get('error', '')

    from sqlalchemy import text
    rows = db.session.execute(text(
        'SELECT COUNT(*) FROM yookassa_payments WHERE user_id = :u'
    ), {'u': parent.id}).fetchone()
    assert rows[0] == 0, 'Заказ для родителя создаваться не должен'

    # Ни у кого Premium не появился
    assert not _plan(child.id)['is_premium']
    assert not _plan(parent.id)['is_premium']


def test_teacher_cannot_buy_for_student(gift_app):
    """Учитель тоже не может купить Premium ученику своей группы."""
    from models import db, T10Group, T10GroupMember

    teacher = _make_user('gift_teacher@example.invalid', 'gift_teacher', role='teacher')
    student = _make_user('gift_student@example.invalid', 'gift_student', role='student')
    g = T10Group(name='Математика', teacher_id=teacher.id, invite_code='ABC123')
    db.session.add(g)
    db.session.commit()
    db.session.add(T10GroupMember(
        group_id=g.id, user_id=student.id, role='student', status='accepted'))
    db.session.commit()

    client = gift_app.test_client()
    _login(client, teacher)

    resp = client.get(f'/payments/premium/checkout?plan=premium_calm&for_user={student.id}')
    assert resp.status_code == 302

    resp = client.post('/payments/premium/create', json={
        'plan': 'premium_calm', 'for_user': student.id,
    })
    assert resp.status_code == 403
    assert 'аккаунте ребёнка' in resp.get_json().get('error', '')

    assert not _plan(student.id)['is_premium']
    assert not _plan(teacher.id)['is_premium']


def test_parent_cannot_buy_for_self(gift_app):
    """Родитель не покупает Premium и в своём аккаунте."""
    parent = _make_user('self_parent@example.invalid', 'self_parent', role='parent')
    client = gift_app.test_client()
    _login(client, parent)

    resp = client.get('/payments/premium/checkout?plan=premium_intense')
    assert resp.status_code == 302

    resp = client.post('/payments/premium/create', json={'plan': 'premium_intense'})
    assert resp.status_code == 403
    assert 'аккаунте ребёнка' in resp.get_json().get('error', '')


def _trial_as_role(email, nickname, role):
    """Пробный день через РЕАЛЬНОЕ приложение (маршрут живёт в app.py).

    Фикстура app в conftest — минимальное приложение без этого маршрута,
    поэтому проверяем на подлинном объекте app.
    """
    import app as real_app_module
    from models import db as _db, User

    rac = real_app_module.app.test_client()
    with real_app_module.app.app_context():
        user = User(email=email, nickname=nickname, role=role, is_guest=False)
        _db.session.add(user)
        _db.session.commit()
        uid = user.id
    with rac.session_transaction() as sess:
        sess['_user_id'] = str(uid)

    resp = rac.post('/api/subscribe/trial', json={'plan': 'premium_intense'})
    from services.subscription import get_subscription_service
    with real_app_module.app.app_context():
        plan = get_subscription_service().get_user_plan(uid)
    return resp, plan


def test_parent_cannot_start_trial():
    """Пробный день Premium родителю тоже закрыт."""
    resp, plan = _trial_as_role('trial_parent@example.invalid',
                                'trial_parent', 'parent')
    assert resp.status_code == 403
    assert 'аккаунте ребёнка' in resp.get_json().get('error', '')
    assert not plan['is_premium']


def test_teacher_cannot_start_trial():
    """Пробный день Premium учителю закрыт."""
    resp, plan = _trial_as_role('trial_teacher@example.invalid',
                                'trial_teacher', 'teacher')
    assert resp.status_code == 403
    assert 'аккаунте ребёнка' in resp.get_json().get('error', '')
    assert not plan['is_premium']


def test_student_pilot_can_buy_for_self(gift_app):
    """Ученик с пилотным id покупает как раньше (демо-режим)."""
    student = _make_user('pilot_student@example.invalid', 'pilot_student',
                         role='student', uid=1)

    client = gift_app.test_client()
    _login(client, student)

    resp = client.get('/payments/premium/checkout?plan=premium_intense')
    assert resp.status_code == 200

    resp = client.post('/payments/premium/create', json={'plan': 'premium_intense'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get('ok') and data.get('demo')

    resp = client.get(f"/payments/premium/return?order_id={data['order_id']}&demo=1")
    assert resp.status_code == 200
    assert _plan(student.id)['is_premium']
    assert _plan(student.id)['plan'] == 'premium_intense'
