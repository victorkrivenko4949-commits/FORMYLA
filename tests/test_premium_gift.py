# -*- coding: utf-8 -*-
"""TARIFFS_SECTIONS_V1 (07.11.2026) — тарифы родителя и учителя.

Роль берётся из первого вопроса анкеты (User.role). Правила:
  * родитель/учитель покупает Premium ТОЛЬКО подарочно для ученика
    (for_user, PREMIUM_GIFT_V1): платит взрослый, Premium — ученику;
  * checkout с валидным for_user — 200; без for_user — редирект на
    свой раздел тарифов (/tariffs/parent, /tariffs/teacher);
  * create без валидного for_user — 403;
  * пробный день (/api/subscribe/trial) — по-прежнему 403;
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

    # base.html зовёт tg_trial_state() — на проде его даёт app.py, тут заглушка
    # (как в test_wish_survey_discount.py / test_probnik_assign.py).
    app.context_processor(lambda: {'tg_trial_state': lambda: {'state': 'hidden'}})

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
    # Flask-Login кеширует g._login_user на уровне контекста приложения,
    # а conftest держит один app-context на весь тест — сбрасываем кеш,
    # иначе следующий запрос «помнит» предыдущего пользователя
    # (как в test_teacher_link_requests.py).
    from flask import g
    try:
        g.pop('_login_user', None)
    except Exception:
        pass
    with client.session_transaction() as s:
        s['_user_id'] = str(user.id)


def _plan(user_id):
    from services.subscription import get_subscription_service
    return get_subscription_service().get_user_plan(user_id)


# ─────────────────── новые правила TARIFFS_SECTIONS_V1 ───────────────────

def test_parent_can_buy_for_child(gift_app):
    """Родитель покупает Premium для подтверждённого ребёнка (подарок)."""
    from models import db, ParentChildLink

    parent = _make_user('gift_parent@example.invalid', 'gift_parent', role='parent')
    child = _make_user('gift_child@example.invalid', 'gift_child', role='student')
    db.session.add(ParentChildLink(
        parent_id=parent.id, child_id=child.id, status='accepted'))
    db.session.commit()

    client = gift_app.test_client()
    _login(client, parent)

    # Checkout с for_user — страница оформления подарка (200)
    resp = client.get(f'/payments/premium/checkout?plan=premium_intense&for_user={child.id}')
    assert resp.status_code == 200

    # Создание платежа — ок (демо-режим), заказ с beneficiary = ребёнок
    resp = client.post('/payments/premium/create', json={
        'plan': 'premium_intense', 'for_user': child.id,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get('ok') and data.get('demo')

    # Возврат с оплаты — Premium активен у РЕБЁНКА, не у родителя
    resp = client.get(f"/payments/premium/return?order_id={data['order_id']}&demo=1")
    assert resp.status_code == 200
    assert _plan(child.id)['is_premium']
    assert _plan(child.id)['plan'] == 'premium_intense'
    assert not _plan(parent.id)['is_premium']


def test_teacher_can_buy_for_student(gift_app):
    """Учитель покупает Premium ученику своей группы."""
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
    assert data.get('ok') and data.get('demo')

    resp = client.get(f"/payments/premium/return?order_id={data['order_id']}&demo=1")
    assert resp.status_code == 200
    assert _plan(student.id)['is_premium']
    assert _plan(student.id)['plan'] == 'premium_calm'
    assert not _plan(teacher.id)['is_premium']


def test_parent_without_for_user_redirected_to_own_tariffs(gift_app):
    """Родитель без for_user — редирект на свой раздел тарифов, не /subscribe."""
    parent = _make_user('self_parent@example.invalid', 'self_parent', role='parent')
    client = gift_app.test_client()
    _login(client, parent)

    resp = client.get('/payments/premium/checkout?plan=premium_intense')
    assert resp.status_code == 302
    assert '/tariffs/parent' in resp.headers['Location']

    resp = client.post('/payments/premium/create', json={'plan': 'premium_intense'})
    assert resp.status_code == 403


def test_teacher_without_for_user_redirected_to_own_tariffs(gift_app):
    """Учитель без for_user — редирект на /tariffs/teacher."""
    teacher = _make_user('self_teacher@example.invalid', 'self_teacher', role='teacher')
    client = gift_app.test_client()
    _login(client, teacher)

    resp = client.get('/payments/premium/checkout?plan=premium_intense')
    assert resp.status_code == 302
    assert '/tariffs/teacher' in resp.headers['Location']

    resp = client.post('/payments/premium/create', json={'plan': 'premium_intense'})
    assert resp.status_code == 403


def test_parent_cannot_buy_for_stranger(gift_app):
    """for_user без подтверждённой связи — покупка не проходит."""
    parent = _make_user('stranger_parent@example.invalid', 'stranger_parent', role='parent')
    stranger = _make_user('stranger_kid@example.invalid', 'stranger_kid', role='student')

    client = gift_app.test_client()
    _login(client, parent)

    resp = client.get(f'/payments/premium/checkout?plan=premium_intense&for_user={stranger.id}')
    assert resp.status_code == 302
    assert '/tariffs/parent' in resp.headers['Location']

    resp = client.post('/payments/premium/create', json={
        'plan': 'premium_intense', 'for_user': stranger.id,
    })
    assert resp.status_code == 403


def test_tariffs_teacher_page(gift_app):
    """Раздел тарифов учителя: только для роли teacher, рендер со списком."""
    from models import db, T10Group, T10GroupMember

    teacher = _make_user('tar_teacher@example.invalid', 'tar_teacher', role='teacher')
    student = _make_user('tar_student@example.invalid', 'tar_student', role='student')
    g = T10Group(name='Физтех', teacher_id=teacher.id, invite_code='ZZZ999')
    db.session.add(g)
    db.session.commit()
    db.session.add(T10GroupMember(
        group_id=g.id, user_id=student.id, role='student', status='accepted'))
    db.session.commit()

    client = gift_app.test_client()
    _login(client, teacher)
    resp = client.get('/tariffs/teacher')
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert 'Тарифы' in body
    assert 'tar_student' in body
    assert 'Купить подписку' in body
    # попап «Как работает подготовка» присутствует и показывается 1 раз
    assert 'hwPopup' in body
    assert 'formyla_how_it_works_seen_teacher' in body

    # Родителю раздел учителя закрыт
    parent = _make_user('tar_parent@example.invalid', 'tar_parent', role='parent')
    _login(client, parent)
    resp = client.get('/tariffs/teacher')
    assert resp.status_code in (302, 403)


def test_tariffs_parent_page(gift_app):
    """Раздел тарифов родителя: только для роли parent, рендер со списком."""
    from models import db, ParentChildLink

    parent = _make_user('tar2_parent@example.invalid', 'tar2_parent', role='parent')
    child = _make_user('tar2_child@example.invalid', 'tar2_child', role='student')
    db.session.add(ParentChildLink(
        parent_id=parent.id, child_id=child.id, status='accepted'))
    db.session.commit()

    client = gift_app.test_client()
    _login(client, parent)
    resp = client.get('/tariffs/parent')
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert 'Тарифы' in body
    assert 'tar2_child' in body
    assert 'Купить подписку' in body
    assert 'hwPopup' in body
    assert 'formyla_how_it_works_seen_parent' in body

    # Учителю раздел родителя закрыт
    teacher = _make_user('tar2_teacher@example.invalid', 'tar2_teacher', role='teacher')
    _login(client, teacher)
    resp = client.get('/tariffs/parent')
    assert resp.status_code in (302, 403)


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
    """Пробный день Premium родителю по-прежнему закрыт."""
    resp, plan = _trial_as_role('trial_parent@example.invalid',
                                'trial_parent', 'parent')
    assert resp.status_code == 403
    assert not plan['is_premium']


def test_teacher_cannot_start_trial():
    """Пробный день Premium учителю по-прежнему закрыт."""
    resp, plan = _trial_as_role('trial_teacher@example.invalid',
                                'trial_teacher', 'teacher')
    assert resp.status_code == 403
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
