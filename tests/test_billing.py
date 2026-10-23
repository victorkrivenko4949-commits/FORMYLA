# -*- coding: utf-8 -*-
"""BILLING_V1 — тесты оплаты. HTTP к ЮKassa замокан (monkeypatch services.billing.yookassa_client).

Запуск: pytest tests/test_billing.py -q
Тест конкурентных webhook (FOR UPDATE) — только на PostgreSQL:
    BILLING_TEST_PG_URL=postgresql+psycopg://user:pass@localhost/formyla_test pytest tests/test_billing.py -q -k concurrent
"""
import os
import threading
from datetime import datetime, timedelta, timezone

import pytest

YK_IP = '185.71.76.5'
BAD_IP = '8.8.8.8'


# ───────────────────────── fixtures ─────────────────────────

@pytest.fixture
def bapp(app, monkeypatch):
    monkeypatch.setenv('BILLING_CREATE_ENABLED', '1')
    monkeypatch.setenv('YOOKASSA_SHOP_ID', 'test_shop')
    monkeypatch.setenv('YOOKASSA_SECRET_KEY', 'test_secret')
    monkeypatch.setenv('YOOKASSA_MODE', 'live')
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://formyla.net')
    monkeypatch.delenv('FAMILY_TEACHER_PLANS_ENABLED', raising=False)
    from routes.billing import install_billing
    import models_billing  # noqa: F401
    from models import db
    from sqlalchemy import text
    install_billing(app)
    db.create_all()
    # ORM-модели для subscriptions в models.py нет (таблицу создаёт migrations/002) — создаём как в conftest.db
    if db.engine.dialect.name == 'postgresql':
        db.session.execute(text("""CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL, plan TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active', started_at TIMESTAMP, expires_at TIMESTAMP,
            payment_method TEXT, payment_id TEXT, amount_rub INTEGER, is_trial INTEGER DEFAULT 0,
            is_beta_access INTEGER DEFAULT 1, created_at TIMESTAMP)"""))
    else:
        db.session.execute(text("""CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, plan TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active', started_at TIMESTAMP, expires_at TIMESTAMP,
            payment_method TEXT, payment_id TEXT, amount_rub INTEGER, is_trial INTEGER DEFAULT 0,
            is_beta_access INTEGER DEFAULT 1, created_at TIMESTAMP)"""))
    db.session.commit()
    return app


@pytest.fixture
def bclient(bapp, test_user):
    c = bapp.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(test_user.id)
        s['_csrf_token'] = 'tok'
    return c


class FakeYK:
    """Мок API ЮKassa: хранит платежи, умеет «падать», уважает Idempotence-Key."""

    def __init__(self):
        self.payments = {}
        self.create_calls = []
        self.fail_create = None
        self.fail_get = None

    def create_payment(self, *, amount_kop, currency, description, return_url, idempotence_key, order_id):
        self.create_calls.append(idempotence_key)
        if self.fail_create:
            raise self.fail_create
        for p in self.payments.values():
            if p['_key'] == idempotence_key:
                return p
        pid = f'pay_{len(self.payments) + 1}'
        from services.billing.yookassa_client import kop_to_value
        p = {'id': pid, 'status': 'pending', 'paid': False, 'test': False,
             'amount': {'value': kop_to_value(amount_kop), 'currency': currency},
             'metadata': {'order_id': order_id}, '_key': idempotence_key, '_return_url': return_url,
             'confirmation': {'type': 'redirect', 'confirmation_url': f'https://yk.test/pay/{pid}'}}
        self.payments[pid] = p
        return p

    def succeed(self, pid, **override):
        p = self.payments[pid]
        p.update({'status': 'succeeded', 'paid': True})
        p.update(override)
        return p

    def get_payment(self, pid):
        if self.fail_get:
            raise self.fail_get
        return self.payments[pid]


@pytest.fixture
def yk(monkeypatch):
    from services.billing import yookassa_client as mod
    fake = FakeYK()
    monkeypatch.setattr(mod, 'create_payment', fake.create_payment)
    monkeypatch.setattr(mod, 'get_payment', fake.get_payment)
    return fake


def _create(client, plan='student_month', **extra):
    body = {'plan_code': plan, 'csrf_token': 'tok'}
    body.update(extra)
    return client.post('/billing/create', json=body, headers={'Accept': 'application/json'})


def _hook(client, pid, order_id, ip=YK_IP, event='payment.succeeded'):
    return client.post('/billing/webhook', json={
        'type': 'notification', 'event': event,
        'object': {'id': pid, 'metadata': {'order_id': order_id}}},
        environ_base={'REMOTE_ADDR': ip})


def _order(oid):
    from models import db
    from models_billing import Order
    db.session.expire_all()
    return db.session.get(Order, oid)


def _subs(uid):
    from sqlalchemy import text
    from models import db
    return db.session.execute(text("SELECT plan, status, payment_id, amount_rub, is_beta_access, started_at, expires_at "
                                   "FROM subscriptions WHERE user_id=:u"), {'u': uid}).fetchall()


def _events(oid):
    from models_billing import AnalyticsEvent
    return AnalyticsEvent.query.filter_by(order_id=oid).all()


# ───────────────────────── tests ─────────────────────────

def test_success_flow(bclient, yk, test_user):
    r = _create(bclient, amount=1, user_id=999)          # сумма и user_id из браузера игнорируются
    assert r.status_code == 200, r.get_json()
    oid = r.get_json()['order_id']
    o = _order(oid)
    assert o.status == 'pending' and o.amount == 49000 and o.payer_user_id == test_user.id
    assert o.beneficiary_user_id == test_user.id and o.founder_applied is False
    assert yk.payments['pay_1']['_return_url'] == f'https://formyla.net/billing/success?order={oid}'
    assert _subs(test_user.id) == []                      # до webhook доступа нет
    yk.succeed('pay_1')
    r = _hook(bclient, 'pay_1', oid)
    assert r.status_code == 200 and r.get_json()['result'] == 'paid'
    o = _order(oid)
    assert o.status == 'paid' and o.paid_at is not None
    subs = _subs(test_user.id)
    assert len(subs) == 1 and subs[0][0] == 'premium_monthly' and subs[0][2] == 'pay_1'
    assert int(subs[0][3]) == 490 and int(subs[0][4] or 0) == 0
    assert len(_events(oid)) == 1


def test_repeat_webhook_is_noop(bclient, yk, test_user):
    oid = _create(bclient).get_json()['order_id']
    yk.succeed('pay_1')
    assert _hook(bclient, 'pay_1', oid).get_json()['result'] == 'paid'
    assert _hook(bclient, 'pay_1', oid).get_json()['result'] == 'already_paid'
    assert len(_subs(test_user.id)) == 1 and len(_events(oid)) == 1


def test_right_ip_wrong_amount_no_access(bclient, yk, test_user):
    oid = _create(bclient).get_json()['order_id']
    yk.succeed('pay_1', amount={'value': '1.00', 'currency': 'RUB'})
    r = _hook(bclient, 'pay_1', oid)
    assert r.status_code == 200 and r.get_json()['result'] == 'mismatch'
    o = _order(oid)
    assert o.status == 'pending' and 'amount_mismatch' in o.note
    assert _subs(test_user.id) == [] and _events(oid) == []


def test_foreign_ip_forbidden(bclient, yk, test_user):
    oid = _create(bclient).get_json()['order_id']
    yk.succeed('pay_1')
    assert _hook(bclient, 'pay_1', oid, ip=BAD_IP).status_code == 403
    assert _order(oid).status == 'pending' and _subs(test_user.id) == []


def test_yookassa_503_keeps_pending(bclient, yk, test_user):
    from services.billing.yookassa_client import YooKassaTemporaryError
    oid = _create(bclient).get_json()['order_id']
    yk.succeed('pay_1')
    yk.fail_get = YooKassaTemporaryError('503')
    assert _hook(bclient, 'pay_1', oid).status_code == 503
    assert _order(oid).status == 'pending' and _subs(test_user.id) == []
    yk.fail_get = None
    assert _hook(bclient, 'pay_1', oid).get_json()['result'] == 'paid'


def test_retry_after_timeout_reuses_idempotence_key(bclient, yk, test_user):
    from services.billing.yookassa_client import YooKassaTemporaryError
    from models_billing import Order
    yk.fail_create = YooKassaTemporaryError('timeout')
    assert _create(bclient).status_code == 503
    o = Order.query.filter_by(payer_user_id=test_user.id).one()
    assert o.status == 'created' and o.yookassa_payment_id is None
    yk.fail_create = None
    r = _create(bclient)
    assert r.status_code == 200 and r.get_json()['order_id'] == o.id
    assert yk.create_calls == [o.idempotence_key, o.idempotence_key]
    assert Order.query.filter_by(payer_user_id=test_user.id).count() == 1
    assert _order(o.id).status == 'pending'


def test_webhook_before_create_response_saved(bclient, yk, test_user):
    """create упал по тайм-ауту ПОСЛЕ того, как ЮKassa создала платёж; webhook приходит раньше повтора."""
    from services.billing.yookassa_client import YooKassaTemporaryError
    from models_billing import Order
    yk.fail_create = YooKassaTemporaryError('timeout')
    assert _create(bclient).status_code == 503
    o = Order.query.filter_by(payer_user_id=test_user.id).one()
    yk.fail_create = None
    p = yk.create_payment(amount_kop=o.amount, currency='RUB', description='x', return_url='x',
                          idempotence_key=o.idempotence_key, order_id=o.id)   # «реальный» платёж ЮKassa
    yk.succeed(p['id'])
    assert _hook(bclient, p['id'], o.id).get_json()['result'] == 'paid'      # заказ найден по metadata.order_id
    o = _order(o.id)
    assert o.status == 'paid' and o.yookassa_payment_id == p['id']
    assert len(_subs(test_user.id)) == 1 and len(_events(o.id)) == 1


def test_crash_between_paid_and_grant_then_retry(bclient, yk, test_user, monkeypatch):
    from services.billing import service
    oid = _create(bclient).get_json()['order_id']
    yk.succeed('pay_1')
    calls = {'n': 0}
    orig = service._grant_access

    def flaky(order):
        calls['n'] += 1
        if calls['n'] == 1:
            raise RuntimeError('db gone')
        return orig(order)
    monkeypatch.setattr(service, '_grant_access', flaky)
    with pytest.raises(RuntimeError):
        service.process_webhook({'object': {'id': 'pay_1', 'metadata': {'order_id': oid}}})
    assert _order(oid).status == 'pending' and _subs(test_user.id) == []
    assert service.process_webhook({'object': {'id': 'pay_1', 'metadata': {'order_id': oid}}}) == 'paid'
    assert len(_subs(test_user.id)) == 1


def test_test_payment_in_live_mode_rejected(bclient, yk, test_user):
    oid = _create(bclient).get_json()['order_id']
    yk.succeed('pay_1', test=True)
    assert _hook(bclient, 'pay_1', oid).get_json()['result'] == 'mismatch'
    assert 'test_payment_in_live' in _order(oid).note and _subs(test_user.id) == []


def test_foreign_order_rejected(bclient, yk, test_user):
    oid = _create(bclient).get_json()['order_id']
    yk.succeed('pay_1', metadata={'order_id': 'someone-else'})
    assert _hook(bclient, 'pay_1', oid).get_json()['result'] == 'mismatch'
    assert _subs(test_user.id) == []


def test_founder_year_period(bapp, test_user):
    from services.billing.catalog import get_product, amount_for
    from services.billing.periods import compute_period
    test_user.is_founder = True
    test_user.founder_price_eligible = True
    assert amount_for(get_product('student_year'), test_user) == (279000, True)
    assert amount_for(get_product('student_month'), test_user) == (39000, True)
    now = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
    starts, ends = compute_period(get_product('student_year'), test_user, now=now)
    assert starts == datetime(2027, 1, 31, 21, 0, tzinfo=timezone.utc)   # 01.02.2027 00:00 МСК
    assert ends == datetime(2028, 1, 31, 21, 0, tzinfo=timezone.utc)     # 01.02.2028 00:00 МСК
    now2 = datetime(2027, 3, 1, 9, 0, tzinfo=timezone.utc)                # после границы — обычное правило
    s2, e2 = compute_period(get_product('student_year'), test_user, now=now2)
    assert s2 == now2 and e2 == datetime(2028, 3, 1, 9, 0, tzinfo=timezone.utc)


def test_founder_year_blocked_when_paid_access_overlaps(bapp, test_user):
    from services.subscription import get_subscription_service
    from services.billing.catalog import get_product
    from services.billing.periods import compute_period, PeriodRuleUnclear
    from models import db
    test_user.is_founder = True
    s = datetime(2026, 11, 1); e = datetime(2027, 3, 1)
    get_subscription_service().activate_premium(test_user.id, 'premium_monthly', payment_id='old',
                                                is_beta=False, amount_rub=490, starts_at=s, expires_at=e)
    db.session.commit()
    with pytest.raises(PeriodRuleUnclear):
        compute_period(get_product('student_year'), test_user, now=datetime(2026, 11, 15, tzinfo=timezone.utc))


def test_period_extends_existing_paid_access(bapp, test_user):
    from services.subscription import get_subscription_service
    from services.billing.catalog import get_product
    from services.billing.periods import compute_period
    from models import db
    now = datetime.utcnow().replace(microsecond=0)
    end = now + timedelta(days=10)
    get_subscription_service().activate_premium(test_user.id, 'premium_monthly', payment_id='old',
                                                is_beta=False, amount_rub=490, starts_at=now, expires_at=end)
    db.session.commit()
    starts, ends = compute_period(get_product('student_month'), test_user)
    assert starts == end.replace(tzinfo=timezone.utc)
    assert ends == starts + timedelta(days=30)


def test_beta_access_does_not_extend(bapp, test_user):
    from services.subscription import get_subscription_service
    from services.billing.catalog import get_product
    from services.billing.periods import compute_period
    from models import db
    get_subscription_service().activate_premium(test_user.id, 'premium_monthly', is_beta=True)
    db.session.commit()
    before = datetime.now(timezone.utc)
    starts, _ = compute_period(get_product('student_month'), test_user)
    assert starts - before < timedelta(seconds=5)


def test_family_month_disabled_400(bclient, yk):
    assert _create(bclient, plan='family_month').status_code == 400


def test_unknown_plan_400(bclient, yk):
    assert _create(bclient, plan='nope').status_code == 400


def test_create_disabled_but_webhook_works(bclient, yk, test_user, monkeypatch):
    oid = _create(bclient).get_json()['order_id']
    monkeypatch.setenv('BILLING_CREATE_ENABLED', '0')
    assert _create(bclient).status_code == 403
    yk.succeed('pay_1')
    assert _hook(bclient, 'pay_1', oid).get_json()['result'] == 'paid'


def test_csrf_required(bclient, yk):
    r = bclient.post('/billing/create', json={'plan_code': 'student_month'}, headers={'Accept': 'application/json'})
    assert r.status_code == 403


def test_success_page_goal_once(bclient, yk, test_user):
    oid = _create(bclient).get_json()['order_id']
    r = bclient.get(f'/billing/success?order={oid}')
    assert r.status_code == 200 and 'Проверяем оплату' in r.get_data(as_text=True)
    yk.succeed('pay_1')
    _hook(bclient, 'pay_1', oid)
    pages = [bclient.get(f'/billing/success?order={oid}').get_data(as_text=True) for _ in range(5)]
    assert sum('data-goal="payment_success"' in p for p in pages) == 1
    assert _events(oid)[0].client_sent_at is not None


def test_success_page_foreign_order_404(bapp, bclient, yk, test_user):
    from models import db, User
    other = User(email='other_bill@example.invalid', nickname='other_bill', is_guest=False)
    db.session.add(other)
    db.session.commit()
    oid = _create(bclient).get_json()['order_id']
    c2 = bapp.test_client()
    with c2.session_transaction() as s:
        s['_user_id'] = str(other.id)
    # conftest держит один app context на всю фикстуру, поэтому g (и current_user)
    # кэшируется между запросами. Запросы «чужого» клиента — в свежем контексте.
    ctx2 = bapp.app_context()
    ctx2.push()
    try:
        assert c2.get(f'/billing/success?order={oid}').status_code == 404
        assert c2.get(f'/billing/status/{oid}').status_code == 404
    finally:
        ctx2.pop()


def test_once_purchase_creates_purchase_row(bclient, yk, test_user):
    from models_billing import Purchase
    oid = _create(bclient, plan='probe_once').get_json()['order_id']
    assert _order(oid).amount == 19900 and _order(oid).access_ends_at is None
    yk.succeed('pay_1')
    assert _hook(bclient, 'pay_1', oid).get_json()['result'] == 'paid'
    assert Purchase.query.filter_by(order_id=oid, product_code='probe_once').count() == 1
    assert _subs(test_user.id) == []


def test_canceled_payment_marks_failed(bclient, yk, test_user):
    oid = _create(bclient).get_json()['order_id']
    yk.payments['pay_1']['status'] = 'canceled'
    assert _hook(bclient, 'pay_1', oid, event='payment.canceled').get_json()['result'] == 'failed'
    assert _order(oid).status == 'failed'


def test_reconcile_fixes_stuck_pending(bclient, yk, test_user):
    from services.billing.service import reconcile
    from models import db
    oid = _create(bclient).get_json()['order_id']
    o = _order(oid)
    o.created_at = datetime.utcnow() - timedelta(minutes=10)
    db.session.commit()
    yk.succeed('pay_1')
    counters = reconcile()
    assert counters['paid'] == 1 and _order(oid).status == 'paid'


def test_paywall_price_from_catalog(bapp, test_user):
    from services.billing.catalog import upgrade_price_label
    assert upgrade_price_label(None) == '490\u00a0₽ за 30 дней'
    test_user.is_founder = True
    assert upgrade_price_label(test_user) == '390\u00a0₽ за 30 дней'


@pytest.mark.skipif(not os.environ.get('BILLING_TEST_PG_URL'), reason='PostgreSQL only (SELECT ... FOR UPDATE)')
def test_concurrent_webhooks_pg(monkeypatch):
    """Два одновременных webhook → один paid, одна подписка, одно событие."""
    from flask import Flask
    from sqlalchemy import text
    from models import db, User
    import models_billing  # noqa: F401
    from models_billing import Order
    from services.billing import service, yookassa_client as mod

    monkeypatch.setenv('YOOKASSA_MODE', 'live')
    app = Flask('pgtest')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['BILLING_TEST_PG_URL']
    app.config['SECRET_KEY'] = 't'
    db.init_app(app)
    with app.app_context():
        db.create_all()
        db.session.execute(text("""CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL, plan TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active', started_at TIMESTAMP, expires_at TIMESTAMP,
            payment_method TEXT, payment_id TEXT, amount_rub INTEGER, is_trial INTEGER DEFAULT 0,
            is_beta_access INTEGER DEFAULT 1, created_at TIMESTAMP)"""))
        db.session.commit()
        u = User(email=f'pg_{datetime.utcnow().timestamp()}@example.invalid', is_guest=False)
        db.session.add(u)
        db.session.commit()
        o = Order(payer_user_id=u.id, beneficiary_user_id=u.id, plan_code='student_month', amount=49000,
                  price_version='t', status='pending', yookassa_payment_id=f'pay_pg_{u.id}',
                  access_starts_at=datetime.utcnow(), access_ends_at=datetime.utcnow() + timedelta(days=30))
        db.session.add(o)
        db.session.commit()
        oid, pid, uid = o.id, o.yookassa_payment_id, u.id

    payment = {'id': pid, 'status': 'succeeded', 'paid': True, 'test': False,
               'amount': {'value': '490.00', 'currency': 'RUB'}, 'metadata': {'order_id': oid}}
    monkeypatch.setattr(mod, 'get_payment', lambda p: payment)
    results, barrier = [], threading.Barrier(2)

    def worker():
        with app.app_context():
            barrier.wait()
            try:
                results.append(service.process_webhook({'object': {'id': pid, 'metadata': {'order_id': oid}}}))
            finally:
                db.session.remove()
    ts = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(results) == ['already_paid', 'paid']
    with app.app_context():
        n_sub = db.session.execute(text("SELECT COUNT(*) FROM subscriptions WHERE user_id=:u"), {'u': uid}).scalar()
        n_ev = db.session.execute(text("SELECT COUNT(*) FROM analytics_events WHERE order_id=:o"), {'o': oid}).scalar()
        assert n_sub == 1 and n_ev == 1
