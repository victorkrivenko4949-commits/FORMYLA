# -*- coding: utf-8 -*-
"""ADMIN_STATS_APP_V1 — раздел «Приложение» (/admin/stats/pwa) и карточка на сводке.

Фикстура как в test_admin_stats_premium.py + таблица pwa_installs.
Запуск: pytest tests/test_admin_stats_app.py -q
"""
import os
import sys
from datetime import datetime, timedelta

import re

import pytest
from sqlalchemy import text

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



PWA_DDL = """CREATE TABLE pwa_installs (id INTEGER PRIMARY KEY, user_id INTEGER, username VARCHAR(120),
    platform VARCHAR(32), source VARCHAR(32), user_agent VARCHAR(300), is_test BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL)"""


def _install(app, uid, platform, is_test=False, days_ago=0):
    with app.app_context():
        app.db.session.execute(text(
            "INSERT INTO pwa_installs (user_id, username, platform, source, is_test, created_at) "
            "VALUES (:u, :n, :p, 'appinstalled', :t, :c)"),
            dict(u=uid, n=f'user{uid}' if uid else None, p=platform, t=is_test,
                 c=datetime.utcnow() - timedelta(days=days_ago)))
        app.db.session.commit()


def _card(html, title):
    m = re.search(re.escape(title) + r'</div>\s*<div class="v[^"]*">([^<]*)</div>', html)
    return m.group(1) if m else None


def test_app_section_without_table(app):
    admin = _mk_user(app, admin=True)
    c = app.test_client()
    c.get(f'/login/{admin}')
    r = c.get('/admin/stats/pwa?p=7')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'Людей с приложением' in html
    assert 'Кому видна кнопка' in html and 'Всем, только Android' in html
    r = c.get('/admin/stats/overview?p=7')
    assert r.status_code == 200 and 'С приложением' in r.get_data(as_text=True)


def test_app_section_counts_people_and_platforms(app):
    admin = _mk_user(app, admin=True)          # 1
    a = _mk_user(app)                           # 2: Android + ПК
    b = _mk_user(app)                           # 3: Android, давно
    t = _mk_user(app)                           # 4: тестовый
    _mk_user(app)                               # 5: без приложения
    with app.app_context():
        app.db.session.execute(text(PWA_DDL))
        app.db.session.commit()
    _install(app, a, 'android')
    _install(app, a, 'desktop')
    _install(app, b, 'android', days_ago=40)
    _install(app, t, 'android', is_test=True)
    _install(app, None, 'ios')

    c = app.test_client()
    c.get(f'/login/{admin}')
    r = c.get('/admin/stats/pwa?p=7')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'Раздел временно недоступен' not in html
    assert _card(html, 'Людей с приложением') == '2'
    assert 'ещё 1 установок без входа' in html
    assert '2 из 5' in html                       # доля от зарегистрированных
    assert _card(html, 'Новых за период') == '1'
    assert _card(html, 'На Android') == '2'
    assert 'Тестовых установок' in html and ': 1 —' in html
    assert 'iPhone' in html and 'Android' in html

    r = c.get('/admin/stats/overview?p=7')
    html = r.get_data(as_text=True)
    assert 'С приложением</div><div class="v">2</div>' in html


def test_app_section_admin_only(app):
    user = _mk_user(app)
    c = app.test_client()
    c.get(f'/login/{user}')
    assert c.get('/admin/stats/pwa').status_code == 403
