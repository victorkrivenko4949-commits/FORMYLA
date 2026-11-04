# -*- coding: utf-8 -*-
"""PREMIUM_PAY_TABLES_FIX (01.11.2026): /payments/premium/create сам создаёт
таблицы платежей (идемпотентный _ensure_tables из routes/yookassa_pay).

Регрессия баги с прода: маршрут вставлял заказ в yookassa_payments, не
вызывая _ensure_tables. На БД без этой таблицы (или без колонки
beneficiary_user_id от PREMIUM_GIFT_V1) INSERT падал с 500
«Не удалось сохранить заказ. Платёж не создавался» — ошибка была бы у
каждого покупателя после открытия продаж 3 ноября.

Запуск: pytest tests/test_premium_create_tables.py -q
"""
import pytest

from routes.yookassa_pay import _ensure_tables


@pytest.fixture
def pay_app(app, monkeypatch):
    """Приложение с premium_pay. Таблицы платежей СОЗНАТЕЛЬНО не создаём:
    проверяем, что маршрут обеспечивает их сам."""
    monkeypatch.delenv('YOOKASSA_SHOP_ID', raising=False)
    monkeypatch.delenv('YOOKASSA_SECRET_KEY', raising=False)

    from routes.premium_pay import install_premium_pay
    from models import db
    install_premium_pay(app)
    db.create_all()
    return app


@pytest.fixture
def pay_user(app):
    """Покупатель — email-пилот (доступ к оплате есть, беты нет)."""
    from models import db, User
    u = User(email='viktorformulevitch@yandex.ru', nickname='buyer',
             is_guest=False)
    db.session.add(u)
    db.session.commit()
    return u


def _reset_ensure_flag(monkeypatch):
    """Флаг _TABLES_ENSURED кэшируется на уровне модуля — сбрасываем,
    чтобы каждый тест шёл по свежей БД без таблиц."""
    monkeypatch.setattr('routes.yookassa_pay._TABLES_ENSURED', False)


def _login(client, user):
    with client.session_transaction() as s:
        s['_user_id'] = str(user.id)


def _create(client, plan='premium_calm'):
    return client.post('/payments/premium/create',
                        json={'plan': plan}, follow_redirects=False)


# ── БД без таблицы yookassa_payments вовсе ───────────────────────────────────

def test_create_ensures_missing_tables(app, pay_app, pay_user, monkeypatch):
    _reset_ensure_flag(monkeypatch)
    client = pay_app.test_client()
    _login(client, pay_user)

    resp = _create(client)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()
    assert data.get('ok') is True
    assert data.get('demo') is True  # ЮKassa не настроена — демо-платёж

    from models import db
    from sqlalchemy import text
    row = db.session.execute(text(
        "SELECT order_id, status, beneficiary_user_id FROM yookassa_payments "
        "WHERE user_id = :u"), {'u': pay_user.id}).fetchone()
    assert row is not None
    assert row[1] == 'succeeded'  # демо-режим сразу отмечает успех
    assert row[2] is None         # обычная покупка — не подарочная


# ── Таблица есть, но БЕЗ колонки beneficiary_user_id (старая схема) ─────────

def test_create_adds_beneficiary_column_to_old_schema(app, pay_app, pay_user,
                                                      monkeypatch):
    from models import db
    from sqlalchemy import text
    with db.engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE yookassa_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id VARCHAR(64) UNIQUE NOT NULL,
                payment_id VARCHAR(128),
                user_id INTEGER NOT NULL,
                item_code VARCHAR(64) NOT NULL DEFAULT 'diamond_badge',
                amount_rub NUMERIC(10, 2) NOT NULL DEFAULT 10.00,
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                confirmation_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP
            )"""))
    _reset_ensure_flag(monkeypatch)
    client = pay_app.test_client()
    _login(client, pay_user)

    resp = _create(client)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json().get('ok') is True

    row = db.session.execute(text(
        "SELECT beneficiary_user_id FROM yookassa_payments "
        "WHERE user_id = :u"), {'u': pay_user.id}).fetchone()
    assert row is not None  # колонка добавлена, заказ сохранён
