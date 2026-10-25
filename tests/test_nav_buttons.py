# -*- coding: utf-8 -*-
"""SURVEYS_NAV_V2 (25.10.2026): где показываются кнопки «📦 База» и «Опросы».

- «📦 База» (admin-base-nav, routes/__init__.py) — на всех старых
  админ-страницах, КРОМЕ раздела «Статистика пользователей» (/admin/users*).
- «Опросы» (ft-surveys-nav, routes/surveys.py) — только в разделе
  «Статистика пользователей» (/admin/users и его подразделы), кроме самой
  страницы опросов.
"""
import pytest
from flask import Flask, Response
from flask_login import LoginManager, UserMixin, login_required

import routes as routes_init
from routes.surveys import install_surveys

HTML = '<html><head><title>t</title></head><body>test</body></html>'


def _make_app():
    app = Flask(__name__)
    app.secret_key = 'test-key'
    lm = LoginManager(app)

    class AdminUser(UserMixin):
        id = 1
        is_admin = True
        is_guest = False

    @lm.user_loader
    def load_user(uid):
        return AdminUser() if uid == '1' else None

    @app.route('/admin/users')
    @app.route('/admin/users/sections')
    @app.route('/admin/users/returns')
    @app.route('/admin/stats/overview')
    @app.route('/admin/support')
    @app.route('/admin/daily')
    @login_required
    def page():
        return Response(HTML, mimetype='text/html')

    # реальные хуки: _admin_base_nav из routes/__init__._install + surveys_ui
    routes_init._install(app)
    install_surveys(app, register=lambda a, bp: a.register_blueprint(bp))
    return app


def _logged_client(app):
    client = app.test_client()
    with client.session_transaction() as s:
        s['_user_id'] = '1'
    return client


CASES = [
    # path, want_base, want_surveys
    ('/admin/users', False, True),
    ('/admin/users/sections', False, True),
    ('/admin/users/returns', False, True),
    ('/admin/stats/overview', True, False),
    ('/admin/support', True, False),
    ('/admin/daily', True, False),
]


@pytest.mark.parametrize('path,want_base,want_surveys', CASES)
def test_admin_buttons_placement(path, want_base, want_surveys):
    client = _logged_client(_make_app())
    body = client.get(path).get_data(as_text=True)
    assert ('admin-base-nav' in body) is want_base, f'База на {path}'
    assert ('ft-surveys-nav' in body) is want_surveys, f'Опросы на {path}'


def test_anonymous_sees_no_buttons():
    client = _make_app().test_client()
    body = client.get('/admin/users').get_data(as_text=True)
    assert 'admin-base-nav' not in body
    assert 'ft-surveys-nav' not in body
