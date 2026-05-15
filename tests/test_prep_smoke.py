# -*- coding: utf-8 -*-
"""
Smoke tests for prep templates (dashboard + wizard).
Verifies pages load with correct status codes and key content.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from flask_login import LoginManager
from models import db as _db, User, OlympiadPrep


@pytest.fixture(scope='module')
def app():
    app = Flask(__name__,
                template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),
                static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static'))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = True
    app.secret_key = 'test-secret'

    # Provide asset_version for templates
    app.jinja_env.globals['asset_version'] = 'test'

    login_manager = LoginManager()
    login_manager.login_view = 'login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return _db.session.get(User, int(user_id))

    # Dummy routes referenced by base.html
    @app.route('/login')
    def login():
        return 'login page', 200

    @app.route('/')
    def index():
        return 'index', 200

    @app.route('/daily')
    def daily_quest_main():
        return 'daily', 200

    @app.route('/olympiads')
    def olympiads():
        return 'olympiads', 200

    @app.route('/leaderboard')
    def leaderboard():
        return 'leaderboard', 200

    @app.route('/profile')
    def profile():
        return 'profile', 200

    @app.route('/logout')
    def logout():
        return 'logout', 200

    @app.route('/secrets')
    def secrets():
        return 'secrets', 200

    # Register blueprints
    from routes.prep import prep_bp
    app.register_blueprint(prep_bp)

    from routes.olympiad_prep import olympiad_prep_bp
    app.register_blueprint(olympiad_prep_bp)

    _db.init_app(app)
    with app.app_context():
        _db.create_all()
        # Seed minimal data
        u = User(id=1, email='smoke@test.ru', name='Smoke User', preferred_grade=9)
        _db.session.add(u)
        o = OlympiadPrep(
            slug='vsosh', name='ВсОШ', short_name='ВсОШ',
            description='Test', grades='[9]',
            stages='[{"name":"Школьный","date_range":"Октябрь"}]',
            official_url='', color_hex='#22d3a6',
            sort_order=1, is_active=True,
        )
        _db.session.add(o)
        _db.session.commit()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = '1'
        sess['_fresh'] = True
    return c


class TestPrepSmoke:

    def test_dashboard_loads(self, auth_client):
        """GET /prep/ with login → 200 + 'Моя подготовка'."""
        resp = auth_client.get('/prep/')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Моя подготовка' in html

    def test_wizard_loads(self, auth_client):
        """GET /prep/new with login → 200 + 'Выбери олимпиаду'."""
        resp = auth_client.get('/prep/new')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Выбери олимпиаду' in html

    def test_dashboard_unauthorized(self, client):
        """GET /prep/ without login → 302 redirect to /login."""
        resp = client.get('/prep/')
        assert resp.status_code in (302, 401)
        if resp.status_code == 302:
            assert '/login' in resp.headers.get('Location', '')
