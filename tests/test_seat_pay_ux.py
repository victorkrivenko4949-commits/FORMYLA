# -*- coding: utf-8 -*-
"""SEAT_PAY_UX_V1 — удобство оплаты подписки на места.

Проверяем:
  • рекомендация тарифа по занятым местам и текущей подписке;
  • /payments/seats/checkout?upgrade=1 открывает следующий тариф;
  • страница оформления содержит переключатель всех тарифов;
  • /payments/seats/status отдаёт JSON и активирует подписку при succeeded;
  • «Платёж не найден» отдаёт 404, а не 500 (раньше — NameError по role);
  • «Оплата отменена» ведёт на повтор с тем же тарифом.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text


def _login(client, user):
    with client.session_transaction() as s:
        s['_user_id'] = str(user.id)


def _no_yookassa(monkeypatch):
    import routes.seat_pay as sp
    import routes.yookassa_pay as yk
    # _TABLES_ENSURED кэшируется на уровне модуля между приложениями
    monkeypatch.setattr(yk, '_TABLES_ENSURED', False)
    monkeypatch.setattr(sp, '_yk_config', lambda: {
        'configured': False, 'shop_id': '', 'secret_key': '',
        'send_receipt': False, 'is_test': False})


def _insert_order(order_id, user_id, plan, status, payment_id=None):
    from models import db
    from routes.yookassa_pay import _ensure_tables
    _ensure_tables()
    db.session.execute(text(
        "INSERT INTO yookassa_payments (order_id, payment_id, user_id, item_code,"
        " amount_rub, status, confirmation_url, created_at, beneficiary_user_id)"
        " VALUES (:oid, :pid, :uid, :item, 1500, :st, NULL, :now, NULL)"
    ), {'oid': order_id, 'pid': payment_id, 'uid': user_id, 'item': plan,
        'st': status, 'now': datetime.utcnow()})
    db.session.commit()


def _give_sub(user_id, plan, seats):
    from models import db
    from routes.seat_pay import _ensure_tables
    _ensure_tables()
    now = datetime.utcnow()
    db.session.execute(text(
        "INSERT INTO seat_subscriptions (user_id, plan, seats, activated_at, expires_at)"
        " VALUES (:uid, :plan, :seats, :now, :exp)"
    ), {'uid': user_id, 'plan': plan, 'seats': seats, 'now': now,
        'exp': now + timedelta(days=10)})
    db.session.commit()


# ── чистые функции ───────────────────────────────────────────────────────

def test_recommend_seat_plan():
    from routes.seat_pay import recommend_seat_plan
    assert recommend_seat_plan(0, 0) == 'seat_one'
    assert recommend_seat_plan(1, 0) == 'seat_start'       # 1 занято → до 5
    assert recommend_seat_plan(5, 0) == 'seat_group'       # 5 занято → до 15
    assert recommend_seat_plan(0, 5) == 'seat_group'       # есть «Старт» → следующий
    assert recommend_seat_plan(0, 15) == 'seat_kruzhok'
    assert recommend_seat_plan(0, 50) == 'seat_kruzhok'    # больше нет — максимум


def test_seats_word():
    from routes.seat_pay import seats_word
    assert seats_word(1) == 'место'
    assert seats_word(3) == 'места'
    assert seats_word(5) == 'мест'
    assert seats_word(15) == 'мест'
    assert seats_word(21) == 'место'


# ── страница оформления ──────────────────────────────────────────────────

def test_checkout_has_plan_switcher_and_default(app, teacher_user, monkeypatch):
    _no_yookassa(monkeypatch)
    with app.test_client() as c:
        _login(c, teacher_user)
        r = c.get('/payments/seats/checkout')
        assert r.status_code == 200
        html = r.data.decode('utf-8')
        for key in ('seat_one', 'seat_start', 'seat_group', 'seat_kruzhok'):
            assert f'data-plan="{key}"' in html
        # учителю без подписки по умолчанию — «Старт»
        assert 'data-plan="seat_start" onclick' in html
        assert 'class="sc-plan on"' in html or ' on"' in html
        assert 'Подходит вам' in html
        assert 'Тестовый режим' in html


def test_checkout_upgrade_opens_next_plan(app, teacher_user, monkeypatch):
    _no_yookassa(monkeypatch)
    _give_sub(teacher_user.id, 'seat_start', 5)
    with app.test_client() as c:
        _login(c, teacher_user)
        r = c.get('/payments/seats/checkout?upgrade=1')
        assert r.status_code == 200
        html = r.data.decode('utf-8')
        # выбран «Группа» (следующий после «Старт»)
        assert 'var scPlan = "seat_group"' in html
        assert 'Следующий' in html
        assert 'Сейчас у вас «Старт»' in html


def test_checkout_student_404(app, test_user, monkeypatch):
    _no_yookassa(monkeypatch)
    with app.test_client() as c:
        _login(c, test_user)
        assert c.get('/payments/seats/checkout').status_code == 404


# ── статус / результат ───────────────────────────────────────────────────

def test_status_not_found_and_foreign(app, teacher_user, parent_user, monkeypatch):
    _no_yookassa(monkeypatch)
    _insert_order('ord_foreign', parent_user.id, 'seat_one', 'pending', 'p1')
    with app.test_client() as c:
        _login(c, teacher_user)
        r = c.get('/payments/seats/status?order_id=nope')
        assert r.status_code == 404
        assert r.get_json()['status'] == 'not_found'
        assert c.get('/payments/seats/status?order_id=ord_foreign').status_code == 403


def test_status_pending_then_succeeded_activates(app, teacher_user, monkeypatch):
    _no_yookassa(monkeypatch)
    from models import db
    from routes.seat_pay import active_seat_sub
    _insert_order('ord_pend', teacher_user.id, 'seat_group', 'pending', 'p2')
    with app.test_client() as c:
        _login(c, teacher_user)
        r = c.get('/payments/seats/status?order_id=ord_pend')
        assert r.status_code == 200 and r.get_json()['status'] == 'pending'
        assert active_seat_sub(teacher_user.id) is None

        # вебхук/ЮKassa подтвердили — статус в БД сменился
        db.session.execute(text(
            "UPDATE yookassa_payments SET status = 'succeeded' WHERE order_id = 'ord_pend'"))
        db.session.commit()
        r = c.get('/payments/seats/status?order_id=ord_pend')
        d = r.get_json()
        assert d['status'] == 'succeeded'
        assert d['redirect'].endswith('/payments/seats/return?order_id=ord_pend')
        sub = active_seat_sub(teacher_user.id)
        assert sub and sub['seats'] == 15

        # повтор — идемпотентно, срок не удваивается
        exp1 = sub['expires_at']
        c.get('/payments/seats/status?order_id=ord_pend')
        assert active_seat_sub(teacher_user.id)['expires_at'] == exp1


def test_return_not_found_is_404_not_500(app, teacher_user, monkeypatch):
    _no_yookassa(monkeypatch)
    from routes.yookassa_pay import _ensure_tables
    _ensure_tables()
    with app.test_client() as c:
        _login(c, teacher_user)
        r = c.get('/payments/seats/return?order_id=does_not_exist')
        assert r.status_code == 404
        html = r.data.decode('utf-8')
        assert 'Платёж не найден' in html
        assert 'does_not_exist' in html


def test_return_canceled_retry_same_plan(app, parent_user, monkeypatch):
    _no_yookassa(monkeypatch)
    _insert_order('ord_canc', parent_user.id, 'seat_one', 'canceled', 'p3')
    with app.test_client() as c:
        _login(c, parent_user)
        r = c.get('/payments/seats/return?order_id=ord_canc')
        assert r.status_code == 200
        html = r.data.decode('utf-8')
        assert 'Оплата не прошла' in html
        assert 'href="/payments/seats/checkout?plan=seat_one"' in html


def test_return_pending_has_autocheck(app, parent_user, monkeypatch):
    _no_yookassa(monkeypatch)
    _insert_order('ord_wait', parent_user.id, 'seat_one', 'pending', 'p4')
    with app.test_client() as c:
        _login(c, parent_user)
        html = c.get('/payments/seats/return?order_id=ord_wait').data.decode('utf-8')
        assert 'Проверяем оплату' in html
        assert '/payments/seats/status?order_id=' in html


def test_demo_flow_end_to_end(app, teacher_user, monkeypatch):
    """Тест-режим без ЮKassa: create → return → подписка активна, кабинет
    ведёт на «Расширить тариф» сразу в оформление."""
    _no_yookassa(monkeypatch)
    with app.test_client() as c:
        _login(c, teacher_user)
        r = c.post('/payments/seats/create', json={'plan': 'seat_start'})
        d = r.get_json()
        assert r.status_code == 200 and d.get('demo') and d.get('redirect')
        r = c.get(d['redirect'])
        html = r.data.decode('utf-8')
        assert r.status_code == 200 and 'Подписка оплачена' in html
        assert '5 мест' in html
        assert 'Добавить учеников →' in html

        r = c.get('/teacher')
        html = r.data.decode('utf-8')
        assert '/payments/seats/checkout?upgrade=1' in html
