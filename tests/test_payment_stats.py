"""Regression: parent/teacher purchases count even without funnel events."""
import json
from datetime import datetime, timedelta

from test_stats_subscriptions_pageviews import app, _user, _admin_client, _sub


def execute(app, sql, **params):
    app.db.session.execute(app.db.text(sql), params)
    app.db.session.commit()


def tables(app):
    execute(app, """CREATE TABLE yookassa_payments (id INTEGER PRIMARY KEY,
        order_id TEXT, payment_id TEXT, user_id INTEGER, beneficiary_user_id INTEGER,
        item_code TEXT, amount_rub NUMERIC, status TEXT, created_at TIMESTAMP, paid_at TIMESTAMP)""")
    execute(app, """CREATE TABLE seat_subscriptions (id INTEGER PRIMARY KEY,
        user_id INTEGER, plan TEXT, activated_at TIMESTAMP, expires_at TIMESTAMP,
        payment_id TEXT, order_id TEXT)""")
    execute(app, """CREATE TABLE orders (id TEXT PRIMARY KEY, yookassa_payment_id TEXT,
        payer_user_id INTEGER, beneficiary_user_id INTEGER, plan_code TEXT,
        amount INTEGER, currency TEXT, status TEXT, is_test BOOLEAN,
        paid_at TIMESTAMP, created_at TIMESTAMP)""")
    execute(app, """CREATE TABLE analytics_events (id INTEGER PRIMARY KEY, order_id TEXT,
        user_id INTEGER, plan_code TEXT, amount INTEGER, is_test BOOLEAN,
        event TEXT, created_at TIMESTAMP)""")
    execute(app, """CREATE TABLE funnel_events (id INTEGER PRIMARY KEY,
        user_id INTEGER, anon_id TEXT, props JSON, event TEXT, source TEXT, created_at TIMESTAMP)""")


def purchase(app, uid, pid, amount=800, plan='seat_one', status='succeeded', when=None,
             beneficiary=None):
    when = when or datetime.utcnow()
    execute(app, """INSERT INTO yookassa_payments
        (order_id, payment_id, user_id, beneficiary_user_id, item_code,
         amount_rub, status, created_at, paid_at)
        VALUES (:oid,:pid,:uid,:b,:plan,:amount,:status,:t,:t)""",
        oid='order-' + pid, pid=pid, uid=uid, b=beneficiary, plan=plan,
        amount=amount, status=status, t=when)


def event(app, uid, pid, amount=800, when=None, order_id=None):
    execute(app, """INSERT INTO funnel_events (user_id, event, props, created_at)
        VALUES (:u,'payment_success',:p,:t)""", u=uid,
        p=json.dumps(dict(payment_id=pid, amount=amount, plan='seat_one', order_id=order_id)),
        t=when or datetime.utcnow())


def test_missing_two_parent_subscriptions_restore_1600(app):
    client = _admin_client(app)
    parents = [_user(app, 'parent-one'), _user(app, 'parent-two')]
    now = datetime.utcnow()
    with app.app_context():
        tables(app)
        for i, uid in enumerate(parents):
            purchase(app, uid, f'parent-{i}')
            execute(app, """INSERT INTO seat_subscriptions
                (user_id,plan,activated_at,expires_at,payment_id,order_id)
                VALUES (:u,'seat_one',:s,:e,:p,:o)""", u=uid, s=now,
                e=now + timedelta(days=30), p=f'parent-{i}', o=f'order-parent-{i}')
        from routes.admin_stats import revenue, msk_today, funnel_counts, subscription_rows
        today = msk_today()
        assert revenue(today, today) == 1600
        assert funnel_counts(today, today)['payment_success'] == 2
        rows = subscription_rows(now)
        assert len(rows) == 2
        assert sum(r['paid_total'] for r in rows) == 1600
        assert sum(r['mrr'] for r in rows) == 1600
        from routes.admin_stats import sources_table
        assert sum(r['payment_success'] for r in sources_table(today, today)) == 2
    html = client.get('/admin/stats/payments?p=today').get_data(as_text=True)
    assert '1 600' in html and 'parent-0' in html and 'parent-1' in html
    assert 'Скачать CSV' in html
    html = client.get('/admin/stats/subscriptions?p=today').get_data(as_text=True)
    assert 'parent-one' in html and 'parent-two' in html and '1 600' in html


def test_deduplicate_ids_preserve_real_payer_and_actual_price(app):
    parent, child = _user(app, 'payer'), _user(app, 'child')
    with app.app_context():
        tables(app)
        purchase(app, parent, 'gift', amount=640, plan='premium_intense', beneficiary=child)
        # Same payment appears in subscriptions with both legacy ID formats,
        # and in repeated/late analytics with a different user and list price.
    _sub(app, child, 'premium_intense', 30, amount=800, pay='yookassa:gift')
    _sub(app, child, 'premium_intense', 30, amount=800, pay='order:order-gift')
    with app.app_context():
        event(app, child, 'gift')
        event(app, child, None, order_id='order-gift')
        from services.payment_stats import payment_query
        rows = payment_query('user_id, beneficiary_user_id, amount_rub, payment_id')
        assert [tuple(r) for r in rows] == [(parent, child, 640, 'gift')]


def test_failed_pending_demo_and_test_orders_do_not_count(app):
    uid = _user(app, 'buyer')
    with app.app_context():
        tables(app)
        for pid, status in [('pending', 'pending'), ('cancelled', 'canceled'),
                            ('demo_payment', 'succeeded')]:
            purchase(app, uid, pid, status=status)
            event(app, uid, pid)
        execute(app, """INSERT INTO orders VALUES
            ('test-order','test-payment',:u,:u,'student_month',49000,'RUB','paid',1,:t,:t)""",
            u=uid, t=datetime.utcnow())
        event(app, uid, 'test-payment')
        from services.payment_stats import payment_query
        assert payment_query('COUNT(*), COALESCE(SUM(amount_rub),0)')[0] == (0, 0)


def test_billing_oneoff_kopecks_renewals_and_legacy_fallback(app):
    uid = _user(app, 'teacher')
    with app.app_context():
        tables(app)
        purchase(app, uid, 'teacher-original', amount=3000, plan='seat_group')
        purchase(app, uid, 'teacher-renewal', amount=3000, plan='seat_group')
        execute(app, """INSERT INTO orders VALUES
            ('oneoff','oneoff-payment',:u,:u,'probe_once',19950,'RUB','paid',0,:t,:t)""",
            u=uid, t=datetime.utcnow())
        execute(app, """INSERT INTO analytics_events
            (order_id,user_id,plan_code,amount,is_test,event,created_at)
            VALUES ('oneoff',:u,'probe_once',19950,0,'payment_success',:t)""",
            u=uid, t=datetime.utcnow())
        event(app, uid, 'oneoff-payment', amount=199.50)
    _sub(app, uid, 'premium_calm', -1, status='expired', amount=500, pay='legacy')
    with app.app_context():
        from services.payment_stats import payment_query
        n, amount = payment_query('COUNT(*), SUM(amount_rub)')[0]
        assert n == 4 and float(amount) == 6699.50


def test_date_filter_after_dedup_and_moscow_boundary(app):
    uid = _user(app, 'buyer')
    with app.app_context():
        tables(app)
        purchase(app, uid, 'before', when=datetime(2026, 11, 15, 20, 59, 59))
        event(app, uid, 'before', when=datetime(2026, 11, 16, 10))
        purchase(app, uid, 'inside', when=datetime(2026, 11, 15, 21))
        purchase(app, uid, 'after', when=datetime(2026, 11, 16, 21))
        from routes.admin_stats import revenue, funnel_by_day
        day = datetime(2026, 11, 16).date()
        assert revenue(day, day) == 800
        assert funnel_by_day(day, day)['2026-11-16']['payment_success'] == 1


def test_csv_contains_entire_period_and_not_just_latest_100(app):
    client = _admin_client(app)
    uid = _user(app, 'buyer')
    with app.app_context():
        tables(app)
        for i in range(101):
            purchase(app, uid, f'purchase-{i}')
        purchase(app, uid, 'old', when=datetime.utcnow() - timedelta(days=60))
    response = client.get('/admin/stats/payments?p=today&csv=1')
    assert response.status_code == 200
    csv = response.get_data(as_text=True)
    assert len(csv.splitlines()) == 102
    assert 'purchase-0;' in csv or 'purchase-0\r' in csv
    assert ';old;' not in csv and ';old\r' not in csv


def test_legacy_iso_timestamp_and_both_subscription_types(app):
    uid = _user(app, 'teacher-and-student')
    when = datetime(2026, 11, 15, 21, 30)
    _sub(app, uid, 'premium_calm', 30, amount=500, pay='personal')
    with app.app_context():
        tables(app)
        execute(app, "UPDATE subscriptions SET created_at = :t", t=when.isoformat())
        purchase(app, uid, 'teacher', amount=1500, plan='seat_start', when=when)
        execute(app, """INSERT INTO seat_subscriptions
            (user_id,plan,activated_at,expires_at,payment_id,order_id)
            VALUES (:u,'seat_start',:s,:e,'teacher','order-teacher')""", u=uid,
            s=when, e=datetime.utcnow() + timedelta(days=30))
        from routes.admin_stats import revenue, subscription_rows
        day = datetime(2026, 11, 16).date()
        assert revenue(day, day) == 2000
        rows = subscription_rows()
        assert len(rows) == 2
        assert sum(r['paid_total'] for r in rows) == 2000
        assert sum(r['mrr'] for r in rows) == 2000
