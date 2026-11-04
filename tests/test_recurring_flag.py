# -*- coding: utf-8 -*-
"""RECURRING_FLAG_V1 (01.11.2026): разовая оплата, пока у магазина в ЮKassa
не включены рекуррентные платежи.

ЮKassa отклоняла любой платёж с save_payment_method=true ошибкой
'This store can't make recurring payments' — у каждого покупателя.
Флаг YOOKASSA_RECURRING_PAYMENTS (по умолчанию выкл) управляет
save_payment_method и копирайтом автопродления.

Запуск: pytest tests/test_recurring_flag.py -q
"""
import json

import pytest

import routes.premium_pay as pp
from routes.yookassa_pay import _ensure_tables


@pytest.fixture
def pay_app(app, monkeypatch):
    monkeypatch.delenv('YOOKASSA_SHOP_ID', raising=False)
    monkeypatch.delenv('YOOKASSA_SECRET_KEY', raising=False)
    monkeypatch.delenv('YOOKASSA_RECURRING_PAYMENTS', raising=False)

    from routes.premium_pay import install_premium_pay
    from models import db
    install_premium_pay(app)
    db.create_all()
    # Флаги «таблицы созданы» кэшируются на уровне модулей, а у каждого
    # теста своя БД — сбрасываем (и после теста), чтобы таблицы создавались.
    import routes.yookassa_pay as _yk
    import services.auto_renew as _ar
    _yk._TABLES_ENSURED = False
    _ar._TABLES_ENSURED = False
    yield app
    _yk._TABLES_ENSURED = False
    _ar._TABLES_ENSURED = False


@pytest.fixture
def pay_user(app):
    from models import db, User
    u = User(email='viktorformulevitch@yandex.ru', nickname='buyer',
             is_guest=False)
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, user):
    with client.session_transaction() as s:
        s['_user_id'] = str(user.id)


class _FakeResp:
    status_code = 200
    content = b'{}'

    def json(self):
        return {'id': 'pay_test', 'status': 'pending',
                'confirmation': {'confirmation_url': 'https://pay.example/1'}}


def _create_with_captured_payload(monkeypatch):
    """Включаем «настоящий» режим ЮKassa и перехватываем payload платежа."""
    monkeypatch.setattr(pp, '_yk_config', lambda: {
        'configured': True, 'shop_id': 'shop', 'secret_key': 'key',
        'send_receipt': False, 'is_test': True})
    captured = {}

    def fake_post(url, auth=None, headers=None, data=None, **kw):
        captured['payload'] = json.loads(data)
        return _FakeResp()

    monkeypatch.setattr(pp.requests, 'post', fake_post)
    return captured


def test_recurring_off_sends_one_time_payment(app, pay_app, pay_user,
                                              monkeypatch):
    """Флаг выключен (по умолчанию): БЕЗ save_payment_method — иначе ЮKassa
    отклоняет платёж ошибкой 'This store can't make recurring payments'."""
    captured = _create_with_captured_payload(monkeypatch)
    client = pay_app.test_client()
    _login(client, pay_user)

    resp = client.post('/payments/premium/create',
                       json={'plan': 'premium_calm'}, follow_redirects=False)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    payload = captured['payload']
    assert payload['save_payment_method'] is False


def test_recurring_on_saves_payment_method(app, pay_app, pay_user,
                                            monkeypatch):
    """Флаг включён: save_payment_method=True — автопродление работает."""
    monkeypatch.setenv('YOOKASSA_RECURRING_PAYMENTS', '1')
    captured = _create_with_captured_payload(monkeypatch)
    client = pay_app.test_client()
    _login(client, pay_user)

    resp = client.post('/payments/premium/create',
                       json={'plan': 'premium_calm'}, follow_redirects=False)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert captured['payload']['save_payment_method'] is True


def test_checkout_shows_one_time_copy_when_disabled(app, pay_app, pay_user):
    """Страница оплаты не обещает автосписания, пока рекуррентные платежи
    магазину не включены."""
    client = pay_app.test_client()
    _login(client, pay_user)

    resp = client.get('/payments/premium/checkout?plan=premium_calm')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Оплата за 30 дней, разовая' in html
    assert 'будут списываться автоматически' not in html


def test_checkout_shows_recurring_copy_when_enabled(app, pay_app, pay_user,
                                                     monkeypatch):
    monkeypatch.setenv('YOOKASSA_RECURRING_PAYMENTS', '1')
    client = pay_app.test_client()
    _login(client, pay_user)

    resp = client.get('/payments/premium/checkout?plan=premium_calm')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Подписка с автопродлением' in html
    assert 'Оплата за 30 дней, разовая' not in html
