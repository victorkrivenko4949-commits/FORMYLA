# -*- coding: utf-8 -*-
"""WISH_SURVEY_V1 — опрос «Что ты хочешь от Формулы?» и скидка 30% на оба тарифа.

Проверяем всю цепочку: ответ → право на скидку → цена на странице →
сумма в заказе и в платеже ЮKassa → сумма в подписке → скидка одноразовая.

Запуск: pytest tests/test_wish_survey_discount.py -q
"""
import pytest
from sqlalchemy import text

from test_premium_gift import _login, _make_user, gift_app  # noqa: F401 (фикстура)

LONG = 'Хочу подготовиться к региональному этапу по математике и понять геометрию'
SHORT = 'Хочу решать задачи'


@pytest.fixture
def wapp(gift_app):  # noqa: F811
    from routes.surveys import install_surveys
    install_surveys(gift_app)
    return gift_app


def _csrf(client):
    r = client.get('/api/wish-survey/pending')
    assert r.status_code == 200
    return r.get_json()


def _answer(client, answer_text):
    token = _csrf(client)['csrf']
    return client.post('/api/wish-survey', json={'answer': answer_text},
                       headers={'X-Wish-CSRF': token})


def _student(client, email='wish@example.invalid', nick='wish_student'):
    u = _make_user(email, nick, role='student')
    _login(client, u)
    return u


def _create(client, plan, expected=None):
    body = {'plan': plan}
    if expected is not None:
        body['expected_amount'] = expected
    return client.post('/payments/premium/create', json=body)


def _order(order_id):
    from models import db
    return db.session.execute(text(
        'SELECT amount_rub, paid_at FROM yookassa_payments WHERE order_id = :o'
    ), {'o': order_id}).fetchone()


# ─────────────────────────── чистая логика ───────────────────────────

def test_discount_math_is_exact():
    from routes.wish_survey import discounted_rub
    assert discounted_rub(800) == 560
    assert discounted_rub(500) == 350
    # ровно 70% от цены (а не «примерно»)
    for base in (800, 500):
        assert discounted_rub(base) * 100 == base * 70


def test_qualifies_needs_more_than_30_chars():
    from routes.wish_survey import qualifies
    assert not qualifies('а' * 30)
    assert qualifies('а' * 31)
    assert not qualifies('.' * 60)                      # без букв — не считается
    assert not qualifies('слово' + ' ' * 40 + 'слово')  # пробелы не накручивают длину
    assert qualifies(LONG)
    assert not qualifies(SHORT)
    assert not qualifies(None)


# ─────────────────────────── опрос ───────────────────────────

def test_pending_and_csrf(wapp):
    client = wapp.test_client()
    _student(client)
    d = _csrf(client)
    assert d['pending'] is True and d['offer'] is True and d['percent'] == 30
    assert {p['amount'] for p in d['prices']} == {560, 350}
    r = client.post('/api/wish-survey', json={'answer': LONG})
    assert r.status_code == 403


def test_long_answer_grants_discount_on_both_plans(wapp):
    from routes.premium_pay import plan_price
    client = wapp.test_client()
    u = _student(client)
    assert plan_price('premium_intense', u.id)['amount'] == 800

    r = _answer(client, LONG)
    assert r.status_code == 200 and r.get_json()['discount'] is True
    assert _csrf(client)['pending'] is False

    assert plan_price('premium_intense', u.id) == {'base': 800, 'amount': 560, 'discount_pct': 30}
    assert plan_price('premium_calm', u.id) == {'base': 500, 'amount': 350, 'discount_pct': 30}


def test_short_answer_no_discount_but_can_improve(wapp):
    from routes.premium_pay import plan_price
    client = wapp.test_client()
    u = _student(client)
    r = _answer(client, SHORT)
    assert r.status_code == 200 and r.get_json()['discount'] is False
    assert plan_price('premium_intense', u.id)['amount'] == 800

    r = _answer(client, LONG)
    assert r.get_json()['discount'] is True
    assert plan_price('premium_intense', u.id)['amount'] == 560

    # выданная скидка не слетает от нового короткого ответа
    _answer(client, SHORT)
    assert plan_price('premium_intense', u.id)['amount'] == 560


def test_gift_purchase_has_no_discount(wapp):
    from routes.premium_pay import plan_price
    client = wapp.test_client()
    u = _student(client)
    _answer(client, LONG)
    assert plan_price('premium_intense', u.id, gift=True)['amount'] == 800


# ─────────────────────────── оплата ───────────────────────────

@pytest.mark.parametrize('plan,base,amount', [
    ('premium_intense', 800, 560),
    ('premium_calm', 500, 350),
])
def test_payment_charges_discounted_amount(wapp, plan, base, amount):
    from models import db
    client = wapp.test_client()
    u = _student(client)
    _answer(client, LONG)

    page = client.get(f'/payments/premium/checkout?plan={plan}').get_data(as_text=True)
    assert f'Оплатить {amount} ₽' in page
    assert f'{base} ₽</s>' in page

    r = _create(client, plan, expected=amount)
    assert r.status_code == 200, r.get_json()
    order_id = r.get_json()['order_id']
    assert int(_order(order_id)[0]) == amount
    disc = db.session.execute(text(
        'SELECT base_rub, amount_rub, user_id FROM wish_discount_orders WHERE order_id = :o'
    ), {'o': order_id}).fetchone()
    assert tuple(disc) == (base, amount, u.id)

    # возврат с оплаты (демо) → Premium активирован, в подписке реальная сумма
    page = client.get(f'/payments/premium/return?order_id={order_id}&demo=1')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert f'class="price">{amount} ₽' in html          # показываем оплаченную сумму
    assert f'class="price">{base} ₽' not in html
    sub = db.session.execute(text(
        'SELECT amount_rub FROM subscriptions WHERE user_id = :u AND plan = :p'
    ), {'u': u.id, 'p': plan}).fetchone()
    assert int(sub[0]) == amount


def test_discount_is_single_use(wapp):
    from routes.premium_pay import plan_price
    client = wapp.test_client()
    u = _student(client)
    _answer(client, LONG)
    order_id = _create(client, 'premium_intense', expected=560).get_json()['order_id']
    client.get(f'/payments/premium/return?order_id={order_id}&demo=1')
    assert _order(order_id)[1] is not None          # оплачен
    assert plan_price('premium_intense', u.id)['amount'] == 800
    assert plan_price('premium_calm', u.id)['amount'] == 500
    assert _csrf(client)['pending'] is False


def test_unpaid_order_does_not_burn_discount(wapp, monkeypatch):
    """Брошенный (неоплаченный) заказ со скидкой не сжигает скидку."""
    from models import db
    from routes.premium_pay import plan_price
    client = wapp.test_client()
    u = _student(client)
    _answer(client, LONG)
    r = _create(client, 'premium_calm', expected=350)
    order_id = r.get_json()['order_id']
    # имитируем «не оплатил»: снимаем отметку об успехе
    db.session.execute(text("UPDATE yookassa_payments SET status = 'canceled', paid_at = NULL "
                            "WHERE order_id = :o"), {'o': order_id})
    db.session.commit()
    assert plan_price('premium_intense', u.id)['amount'] == 560


def test_price_mismatch_blocks_payment(wapp):
    """Человек видел 800 ₽, а сервер насчитал 560 (или наоборот) — платёж не создаётся."""
    from models import db
    client = wapp.test_client()
    _student(client)
    _answer(client, LONG)
    r = _create(client, 'premium_intense', expected=800)
    assert r.status_code == 409
    d = r.get_json()
    assert d['price_changed'] is True and d['amount'] == 560
    n = db.session.execute(text('SELECT COUNT(*) FROM yookassa_payments')).scalar()
    assert n == 0


def test_no_discount_without_answer(wapp):
    client = wapp.test_client()
    _student(client)
    r = _create(client, 'premium_intense', expected=800)
    assert r.status_code == 200
    assert int(_order(r.get_json()['order_id'])[0]) == 800


def test_yookassa_payload_uses_discounted_amount(wapp, monkeypatch):
    """В реальный запрос к ЮKassa уходит именно сумма со скидкой (и в чек тоже)."""
    import json as _json
    import routes.premium_pay as pp

    monkeypatch.setattr(pp, '_yk_config', lambda: {
        'configured': True, 'shop_id': 's', 'secret_key': 'k',
        'send_receipt': True, 'is_test': True})
    sent = {}

    class _Resp:
        status_code = 200
        content = b'1'

        def json(self):
            return {'id': 'pay_1', 'status': 'pending',
                    'confirmation': {'confirmation_url': 'https://yoomoney.example/pay'}}

    def _post(url, auth=None, headers=None, data=None, timeout=None):
        sent['payload'] = _json.loads(data.decode('utf-8'))
        return _Resp()

    monkeypatch.setattr(pp.requests, 'post', _post)
    client = wapp.test_client()
    _student(client, email='wish_yk@example.invalid', nick='wish_yk')
    _answer(client, LONG)
    r = _create(client, 'premium_intense', expected=560)
    assert r.status_code == 200, r.get_json()
    p = sent['payload']
    assert p['amount'] == {'value': '560.00', 'currency': 'RUB'}
    assert p['receipt']['items'][0]['amount'] == {'value': '560.00', 'currency': 'RUB'}
    assert 'скидка 30%' in p['description']


def test_survey_state(wapp):
    from routes.wish_survey import survey_state
    c = wapp.test_client()
    u = _student(c)
    assert survey_state(u.id)['available'] is False
    _answer(c, LONG)
    assert survey_state(u.id) == {'answered': True, 'granted': True, 'available': True, 'used': False}


def test_full_price_result_page_unchanged(wapp):
    """Без скидки страница результата показывает обычную цену."""
    client = wapp.test_client()
    _student(client)
    order_id = _create(client, 'premium_calm', expected=500).get_json()['order_id']
    html = client.get(f'/payments/premium/return?order_id={order_id}&demo=1').get_data(as_text=True)
    assert 'class="price">500 ₽' in html


def test_ensure_tables_survives_parallel_create(wapp, monkeypatch):
    """Гонка воркеров при создании таблиц не роняет запрос, если таблицы уже есть."""
    from flask import current_app
    import routes.wish_survey as ws
    ws.ensure_tables()                                   # таблицы созданы
    current_app.extensions.pop('wish_survey_schema_engine', None)
    real_text = ws.text
    calls = {'n': 0}

    def flaky_text(sql):
        if 'CREATE TABLE' in sql and calls['n'] == 0:
            calls['n'] += 1
            raise RuntimeError('duplicate key value violates unique constraint "pg_type_typname_nsp_index"')
        return real_text(sql)

    monkeypatch.setattr(ws, 'text', flaky_text)
    ws.ensure_tables()                                   # не падает
    assert calls['n'] == 1


def test_admin_stats(wapp):
    from routes.wish_survey import load_admin_stats
    c = wapp.test_client()
    _student(c)
    _answer(c, LONG)
    s = load_admin_stats()
    assert s['total'] == 1 and s['granted'] == 1 and s['used'] == 0
    assert s['rows'][0]['answer_text'] == LONG
