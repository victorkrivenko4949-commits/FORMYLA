# -*- coding: utf-8 -*-
"""PREMIUM_GIFT_V1 — покупка Premium родителем/учителем ДЛЯ ребёнка.

Полный цикл в демо-режиме (ЮKassa не настроена — платёж без списания):
  * родитель открывает checkout?for_user=<ребёнок> по подтверждённой связи;
  * create → заказ с beneficiary_user_id;
  * return → Premium активируется ИМЕННО ребёнку (не платящему).

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
    """Пользователь с ЯВНЫМ id: id=1/5/7452 — пилотные (services/pilot.py),
    и тогда проверка доступа уходит в ветку пилота, а не подарка."""
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


# ───────────────────────── полный поток (демо-режим) ──────────────────────

def test_parent_gift_full_flow(gift_app):
    """Родитель платит — Premium получает РЕБЁНОК, а не родитель."""
    from models import db, ParentChildLink

    parent = _make_user('gift_parent@example.invalid', 'gift_parent', role='parent')
    child = _make_user('gift_child@example.invalid', 'gift_child', role='student')
    db.session.add(ParentChildLink(
        parent_id=parent.id, child_id=child.id, status='accepted'))
    db.session.commit()

    client = gift_app.test_client()
    _login(client, parent)

    # 1) Страница оформления: доступна, показывает получателя
    resp = client.get(f'/payments/premium/checkout?plan=premium_intense&for_user={child.id}')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'gift_child' in body
    assert 'для ученика' in body

    # 2) Создание платежа: заказ с beneficiary_user_id = ребёнок
    resp = client.post('/payments/premium/create', json={
        'plan': 'premium_intense', 'for_user': child.id,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get('ok') and data.get('demo')
    order_id = data['order_id']

    from sqlalchemy import text
    row = db.session.execute(text(
        'SELECT user_id, item_code, beneficiary_user_id FROM yookassa_payments WHERE order_id = :o'
    ), {'o': order_id}).fetchone()
    assert row is not None
    assert row[0] == parent.id          # платит родитель
    assert row[1] == 'premium_intense'
    assert row[2] == child.id            # получатель — ребёнок

    # 3) Возврат с оплаты: активация Premium именно ребёнку
    resp = client.get(f'/payments/premium/return?order_id={order_id}&demo=1')
    assert resp.status_code == 200

    child_plan = _plan(child.id)
    parent_plan = _plan(parent.id)
    assert child_plan['is_premium'], 'Premium должен быть у ребёнка'
    assert child_plan['plan'] == 'premium_intense'
    assert not parent_plan['is_premium'], 'У платящего родителя Premium быть не должно'

    # 4) Повторное открытие ссылки — идемпотентно (срок не переписывается)
    expires_before = _plan(child.id)['expires_at']
    resp = client.get(f'/payments/premium/return?order_id={order_id}&demo=1')
    assert resp.status_code == 200
    assert _plan(child.id)['expires_at'] == expires_before


def test_teacher_gift_for_group_student(gift_app):
    """Учитель может купить Premium ученику своей группы (accepted)."""
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
    assert resp.status_code == 200

    resp = client.post('/payments/premium/create', json={
        'plan': 'premium_calm', 'for_user': student.id,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get('ok')
    resp = client.get(f"/payments/premium/return?order_id={data['order_id']}&demo=1")
    assert resp.status_code == 200

    assert _plan(student.id)['is_premium']
    assert _plan(student.id)['plan'] == 'premium_calm'
    assert not _plan(teacher.id)['is_premium']


def test_pending_link_not_enough(gift_app):
    """Без подтверждения ребёнком связи покупка недоступна (404)."""
    from models import db, ParentChildLink

    parent = _make_user('pend_parent@example.invalid', 'pend_parent', role='parent')
    child = _make_user('pend_child@example.invalid', 'pend_child', role='student')
    db.session.add(ParentChildLink(
        parent_id=parent.id, child_id=child.id, status='pending'))
    db.session.commit()

    client = gift_app.test_client()
    _login(client, parent)

    resp = client.get(f'/payments/premium/checkout?for_user={child.id}')
    assert resp.status_code == 404
    resp = client.post('/payments/premium/create', json={
        'plan': 'premium_intense', 'for_user': child.id})
    assert resp.status_code == 404


def test_foreign_parent_cannot_buy(gift_app):
    """Чужой родитель не может купить Premium несвязанному ребёнку."""
    parent = _make_user('other_parent@example.invalid', 'other_parent', role='parent')
    child = _make_user('alien_child@example.invalid', 'alien_child', role='student')

    client = gift_app.test_client()
    _login(client, parent)

    resp = client.get(f'/payments/premium/checkout?for_user={child.id}')
    assert resp.status_code == 404
    resp = client.post('/payments/premium/create', json={
        'plan': 'premium_intense', 'for_user': child.id})
    assert resp.status_code == 404


def test_cannot_buy_for_self_via_for_user(gift_app):
    """for_user=self — не подарочная покупка, доступ запрещён (не пилот)."""
    user = _make_user('selfy@example.invalid', 'selfy', role='student')
    client = gift_app.test_client()
    _login(client, user)
    resp = client.get(f'/payments/premium/checkout?for_user={user.id}')
    assert resp.status_code == 404


def test_child_with_premium_blocks_repeat_purchase(gift_app):
    """Если у ребёнка уже есть Premium — повторная оплата не создаётся."""
    from models import db, ParentChildLink
    from services.subscription import get_subscription_service

    parent = _make_user('rp_parent@example.invalid', 'rp_parent', role='parent')
    child = _make_user('rp_child@example.invalid', 'rp_child', role='student')
    db.session.add(ParentChildLink(
        parent_id=parent.id, child_id=child.id, status='accepted'))
    db.session.commit()
    get_subscription_service().activate_premium(
        child.id, plan='premium_intense', is_beta=False)
    from models import db
    db.session.commit()  # сервис сознательно не коммитит сам

    client = gift_app.test_client()
    _login(client, parent)

    resp = client.get(f'/payments/premium/checkout?for_user={child.id}')
    assert resp.status_code == 200
    assert 'уже активен' in resp.get_data(as_text=True)

    resp = client.post('/payments/premium/create', json={
        'plan': 'premium_intense', 'for_user': child.id})
    assert resp.status_code == 409
