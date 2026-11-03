# -*- coding: utf-8 -*-
"""ADMIN_STATS_PREMIUM_V1 — счётчик «людей с Premium-доступом» в статистике.

Считает как services.pilot.has_premium_access: пилотные аккаунты +
активные подписки «Работяга»/«Спокойный». Мини-приложение как в
test_funnel_admin_stats.py, но у users есть email и есть таблица subscriptions.

Запуск: pytest tests/test_admin_stats_premium.py -q
"""
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('ADMIN_STATS_ENABLED', '1')
os.environ['ADMIN_BASE_AUTOREG'] = '0'


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from flask import Flask
    from flask_login import LoginManager, UserMixin, login_user
    from flask_sqlalchemy import SQLAlchemy
    import types

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tpl = tmp_path / 'templates'
    (tpl / 'admin').mkdir(parents=True)
    (tpl / 'base.html').write_text(
        '<!DOCTYPE html><html><head>{% block extra_css %}{% endblock %}</head>'
        '<body>{% block content %}{% endblock %}</body></html>', encoding='utf-8')
    import shutil
    for name in os.listdir(os.path.join(root, 'templates', 'admin')):
        if name.startswith('stats_'):
            shutil.copy(os.path.join(root, 'templates', 'admin', name), tpl / 'admin' / name)
    app = Flask(__name__, template_folder=str(tpl))
    app.config.update(SECRET_KEY='t', TESTING=True,
                      SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path/'t.db'}",
                      SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db = SQLAlchemy(app)

    class User(UserMixin, db.Model):
        __tablename__ = 'users'
        id = db.Column(db.Integer, primary_key=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        email = db.Column(db.String(128))
        role = db.Column(db.String(16), default='student')
        is_guest = db.Column(db.Boolean, default=False)
        admin = db.Column(db.Boolean, default=False)

        @property
        def is_admin(self):
            return bool(self.admin)

    class Subscription(db.Model):
        __tablename__ = 'subscriptions'
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer)
        plan = db.Column(db.String(32))
        status = db.Column(db.String(16), default='active')
        expires_at = db.Column(db.DateTime)
        is_beta_access = db.Column(db.Boolean, default=False)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        amount_rub = db.Column(db.Integer)
        payment_id = db.Column(db.String(64))

    fake_models = types.ModuleType('models')
    fake_models.db = db
    fake_models.User = User
    monkeypatch.setitem(sys.modules, 'models', fake_models)

    lm = LoginManager(app)

    @lm.user_loader
    def load(uid):
        return db.session.get(User, int(uid))

    @app.route('/login/<int:uid>')
    def do_login(uid):
        login_user(db.session.get(User, uid))
        return 'ok'

    with app.app_context():
        db.create_all()

    from routes import admin_stats
    admin_stats.install(app)

    app.User = User
    app.Subscription = Subscription
    app.db = db
    return app


def _mk_user(app, email=None, admin=False):
    with app.app_context():
        u = app.User(email=email, admin=admin)
        app.db.session.add(u)
        app.db.session.commit()
        return u.id


def _mk_sub(app, user_id, plan, status='active', expires=None, beta=False):
    with app.app_context():
        s = app.Subscription(user_id=user_id, plan=plan, status=status,
                             expires_at=expires, is_beta_access=beta)
        app.db.session.add(s)
        app.db.session.commit()
        return s.id


def test_premium_users_counts_pilots_and_active_subs(app):
    """Идёт в счёт: пилот по id и активный «Спокойный»; не идут: истёкшая
    подписка, чужой тариф, обычный пользователь.

    Важно: первые пользователи получают id 1–4, пилотный id=5 из
    services/pilot.py никто не занимает (иначе счёт слетит).
    """
    pilot_admin = _mk_user(app, email='pilot@example.invalid', admin=True)  # id=1 → пилот
    buyer = _mk_user(app, email='buyer@example.invalid')                   # id=2
    expired = _mk_user(app, email='expired@example.invalid')               # id=3
    other = _mk_user(app, email='other@example.invalid')                  # id=4
    assert pilot_admin == 1

    _mk_sub(app, buyer, 'premium_calm', expires=datetime.utcnow() + timedelta(days=20))
    _mk_sub(app, expired, 'premium_intense', expires=datetime.utcnow() - timedelta(days=1))
    _mk_sub(app, other, 'student_month', expires=datetime.utcnow() + timedelta(days=20))

    with app.test_request_context('/admin/stats/overview'):
        from routes.admin_stats import premium_users
        got = premium_users()
    assert got == {'total': 2, 'pilots': 1, 'subscribed': 1}


def test_premium_users_no_pilot_double_count(app):
    """Пилот с активной подпиской считается один раз (UNION)."""
    pilot = _mk_user(app, email='pilot2@example.invalid')
    assert pilot == 1
    _mk_sub(app, pilot, 'premium_intense', expires=datetime.utcnow() + timedelta(days=5))
    with app.test_request_context('/admin/stats/overview'):
        from routes.admin_stats import premium_users
        got = premium_users()
    assert got['total'] == 1 and got['pilots'] == 1 and got['subscribed'] == 1


def test_overview_and_subscriptions_show_premium_card(app):
    admin = _mk_user(app, email='adm@example.invalid', admin=True)   # id=1 (пилот)
    buyer = _mk_user(app, email='b@example.invalid')                 # id=2
    _mk_sub(app, buyer, 'premium_calm', expires=datetime.utcnow() + timedelta(days=20))

    c = app.test_client()
    c.get(f'/login/{admin}')
    r = c.get('/admin/stats/overview?p=7')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'С Premium-доступом' in html
    assert '<div class="v">2</div>' in html          # пилот id=1 + покупатель
    assert 'пилоты: 1' in html and 'по тарифу: 1' in html

    r = c.get('/admin/stats/subscriptions?p=7')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'Людей с Premium-доступом' in html
    assert 'Спокойный / мес (500 ₽)' in html
