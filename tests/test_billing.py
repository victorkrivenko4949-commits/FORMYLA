# -*- coding: utf-8 -*-
"""BILLING_V1 — тесты витрины, создания платежа и webhook ЮKassa на мини-приложении (SQLite, моки HTTP).

Запуск: pytest tests/test_billing.py -q
"""
import json
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['ADMIN_BASE_AUTOREG'] = '0'
os.environ['BILLING_ENABLED'] = '1'
os.environ['FUNNEL_ENABLED'] = '1'
os.environ['YOOKASSA_SHOP_ID'] = 'test_shop'
os.environ['YOOKASSA_SECRET_KEY'] = 'test_key'
os.environ['YOOKASSA_SKIP_IP_CHECK'] = '0'


class _Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'http {self.status_code}')


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from flask import Flask
    from flask_login import LoginManager, UserMixin, login_user
    from flask_sqlalchemy import SQLAlchemy
    import types, shutil

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tpl = tmp_path / 'templates'
    (tpl / 'billing').mkdir(parents=True)
    (tpl / 'base.html').write_text('<html><head>{% block extra_css %}{% endblock %}</head>'
                                   '<body>{% block content %}{% endblock %}</body></html>', encoding='utf-8')
    for name in os.listdir(os.path.join(root, 'templates', 'billing')):
        shutil.copy(os.path.join(root, 'templates', 'billing', name), tpl / 'billing' / name)

    app = Flask(__name__, template_folder=str(tpl))
    app.config.update(SECRET_KEY='t', TESTING=True, SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path/'b.db'}",
                      SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db = SQLAlchemy(app)

    class User(UserMixin, db.Model):
        __tablename__ = 'users'
        id = db.Column(db.Integer, primary_key=True)
        email = db.Column(db.String(120))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        is_guest = db.Column(db.Boolean, default=False)
        current_plan = db.Column(db.String(32), default='free')
        plan_expires_at = db.Column(db.String(40))

    fake = types.ModuleType('models'); fake.db = db; fake.User = User
    monkeypatch.setitem(sys.modules, 'models', fake)
    lm = LoginManager(app)

    @lm.user_loader
    def load(uid):
        return db.session.get(User, int(uid))

    with app.app_context():
        db.create_all()
        db.session.execute(db.text("""CREATE TABLE subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, plan TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active', started_at TIMESTAMP, expires_at TIMESTAMP, payment_method TEXT,
            payment_id TEXT, amount_rub INTEGER, is_trial INTEGER DEFAULT 0, is_beta_access INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""))
        db.session.execute(db.text("""CREATE TABLE usage_daily (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            date DATE, tasks_completed INTEGER DEFAULT 0, ai_explanations_used INTEGER DEFAULT 0,
            tokens_consumed INTEGER DEFAULT 0, cost_usd REAL DEFAULT 0, UNIQUE(user_id, date))"""))
        db.session.commit()

    @app.route('/login/<int:uid>')
    def do_login(uid):
        login_user(db.session.get(User, uid)); return 'ok'

    from services import funnel, payments_yookassa as yk
    funnel._tables_ready = False
    yk._ready = False
    funnel.install(app)
    from routes import billing
    billing.install(app)
    app.User, app.db = User, db
    return app


def _user(app, created=None, email='u@example.com'):
    with app.app_context():
        u = app.User(email=email, created_at=created or datetime.utcnow())
        app.db.session.add(u); app.db.session.commit(); return u.id


def test_subscribe_page_prices_for_founder_and_new(app):
    founder = _user(app, created=datetime(2026, 10, 1))
    newbie = _user(app, created=datetime(2026, 11, 5), email='n@example.com')
    c = app.test_client(); c.get(f'/login/{founder}')
    html = c.get('/subscribe?from=daily_limit').get_data(as_text=True)
    assert 'Вы — Основатель' in html and '2 790' in html and '390 ₽' in html
    c2 = app.test_client(); c2.get(f'/login/{newbie}')
    html2 = c2.get('/subscribe').get_data(as_text=True)
    assert 'Вы — Основатель' not in html2 and '2 990' in html2 and '490 ₽' in html2
    assert c.get('/billing/status.json').get_json()['is_founder'] is True


def test_create_payment_redirects(app, monkeypatch):
    uid = _user(app)
    from services import payments_yookassa as yk
    calls = {}

    class FakeReq:
        @staticmethod
        def post(url, headers=None, data=None, timeout=None):
            body = json.loads(data); calls['body'] = body; calls['idem'] = headers.get('Idempotence-Key')
            return _Resp({'id': 'pay-123', 'status': 'pending',
                          'confirmation': {'confirmation_url': 'https://yoomoney.ru/checkout/pay-123'}})
    monkeypatch.setattr(yk, '_http', lambda: FakeReq)
    c = app.test_client(); c.get(f'/login/{uid}')
    r = c.post('/billing/create', data={'plan': 'student_year'})
    assert r.status_code == 302 and 'pay-123' in r.headers['Location']
    assert calls['body']['amount']['value'] == '2790.00'   # пользователь создан сейчас (до 01.11) → Основатель
    assert calls['body']['metadata'] == {'user_id': str(uid), 'plan': 'student_year', 'founder': '1'}
    assert calls['idem']
    assert c.post('/billing/create', data={'plan': 'nope'}).status_code == 400
    with app.app_context():
        row = app.db.session.execute(app.db.text("SELECT status, plan FROM payments WHERE payment_id='pay-123'")).first()
    assert row[0] == 'pending' and row[1] == 'student_year'


def _webhook(c, payment_id, ip='185.71.76.5'):
    return c.post('/billing/webhook', json={'type': 'notification', 'event': 'payment.succeeded',
                                            'object': {'id': payment_id, 'status': 'succeeded'}},
                  headers={'X-Forwarded-For': ip})


def test_webhook_activates_once_and_rejects_foreign_ip(app, monkeypatch):
    uid = _user(app)
    from services import payments_yookassa as yk
    fetched = {'n': 0}

    class FakeReq:
        @staticmethod
        def get(url, headers=None, timeout=None):
            fetched['n'] += 1
            return _Resp({'id': 'pay-9', 'status': 'succeeded', 'amount': {'value': '2790.00', 'currency': 'RUB'},
                          'metadata': {'user_id': str(uid), 'plan': 'student_year'}})
    monkeypatch.setattr(yk, '_http', lambda: FakeReq)
    c = app.test_client()
    assert _webhook(c, 'pay-9', ip='8.8.8.8').status_code == 403
    r = _webhook(c, 'pay-9')
    assert r.status_code == 200 and r.get_json()['reason'] == 'fulfilled'
    r2 = _webhook(c, 'pay-9')
    assert r2.get_json()['reason'] == 'already_processed' and fetched['n'] == 1
    with app.app_context():
        subs = app.db.session.execute(app.db.text(
            "SELECT plan, status, is_beta_access, amount_rub FROM subscriptions WHERE user_id=:u"), {'u': uid}).fetchall()
        pays = app.db.session.execute(app.db.text("SELECT COUNT(*) FROM funnel_events WHERE event='payment_success'")).scalar()
    assert len(subs) == 1 and subs[0][0] == 'premium_yearly' and subs[0][1] == 'active' and subs[0][2] == 0 and subs[0][3] == 2790
    assert pays == 1
    from services.subscription import get_subscription_service
    with app.app_context():
        plan = get_subscription_service().get_user_plan(uid)
    assert plan['is_premium'] and plan['plan'] == 'premium_yearly'


def test_webhook_one_time_and_family_plan(app, monkeypatch):
    uid = _user(app)
    from services import payments_yookassa as yk
    store = {'pay-a': ('probe_once', '199.00'), 'pay-b': ('family_month', '890.00')}

    class FakeReq:
        @staticmethod
        def get(url, headers=None, timeout=None):
            pid = url.rsplit('/', 1)[-1]; plan, amt = store[pid]
            return _Resp({'id': pid, 'status': 'succeeded', 'amount': {'value': amt, 'currency': 'RUB'},
                          'metadata': {'user_id': str(uid), 'plan': plan}})
    monkeypatch.setattr(yk, '_http', lambda: FakeReq)
    c = app.test_client()
    assert _webhook(c, 'pay-a').get_json()['reason'] == 'fulfilled'
    assert _webhook(c, 'pay-b').get_json()['reason'] == 'fulfilled'
    with app.app_context():
        pur = app.db.session.execute(app.db.text("SELECT product, amount FROM purchases WHERE user_id=:u"), {'u': uid}).fetchall()
        from services.subscription import get_subscription_service
        plan = get_subscription_service().get_user_plan(uid)
    assert pur[0][0] == 'probe_once' and float(pur[0][1]) == 199.0
    assert plan['plan'] == 'family_monthly' and plan['is_premium'] and plan['display_name'] == 'Семья'


def test_webhook_unknown_plan_and_canceled(app, monkeypatch):
    uid = _user(app)
    from services import payments_yookassa as yk

    class FakeReq:
        @staticmethod
        def get(url, headers=None, timeout=None):
            pid = url.rsplit('/', 1)[-1]
            if pid == 'pay-x':
                return _Resp({'id': pid, 'status': 'succeeded', 'amount': {'value': '1.00'}, 'metadata': {'user_id': str(uid), 'plan': 'weird'}})
            return _Resp({'id': pid, 'status': 'canceled', 'amount': {'value': '490.00'}, 'metadata': {'user_id': str(uid), 'plan': 'student_month'}})
    monkeypatch.setattr(yk, '_http', lambda: FakeReq)
    c = app.test_client()
    assert _webhook(c, 'pay-x').get_json()['reason'] == 'unknown_plan'
    assert _webhook(c, 'pay-c').get_json()['reason'] == 'status_canceled'
    with app.app_context():
        from services.subscription import get_subscription_service
        assert get_subscription_service().get_user_plan(uid)['plan'] == 'free'
        st = app.db.session.execute(app.db.text("SELECT status FROM payments WHERE payment_id='pay-c'")).scalar()
    assert st == 'canceled'


def test_cancel_subscription(app, monkeypatch):
    uid = _user(app)
    c = app.test_client(); c.get(f'/login/{uid}')
    with app.app_context():
        from services.subscription import get_subscription_service
        get_subscription_service().activate_premium(uid, 'premium_monthly', is_beta=True)
        app.db.session.commit()
    r = c.post('/billing/cancel', json={})
    assert r.get_json()['ok'] is True
    with app.app_context():
        st = app.db.session.execute(app.db.text("SELECT status FROM subscriptions WHERE user_id=:u ORDER BY id DESC LIMIT 1"), {'u': uid}).scalar()
    assert st == 'cancelled'
    assert c.get('/billing/success').status_code == 200
