# -*- coding: utf-8 -*-
"""FUNNEL_V1 / ADMIN_STATS_V1 — изолированные тесты на мини-приложении Flask + SQLite.

Запуск: pytest tests/test_funnel_admin_stats.py -q
Не трогают production-модели: таблица users создаётся минимальная.
"""
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('FUNNEL_ENABLED', '1')
os.environ.setdefault('ADMIN_STATS_ENABLED', '1')
os.environ['ADMIN_BASE_AUTOREG'] = '0'   # не тянуть весь автохук routes/__init__


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from flask import Flask, Blueprint, jsonify
    from flask_login import LoginManager, UserMixin, login_user
    from flask_sqlalchemy import SQLAlchemy
    import types

    # изолированные шаблоны: минимальный base.html + реальные admin/stats_*.html
    import shutil
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tpl = tmp_path / 'templates'
    (tpl / 'admin').mkdir(parents=True)
    (tpl / 'base.html').write_text(
        '<!DOCTYPE html><html><head>{% block extra_css %}{% endblock %}</head>'
        '<body>{% block content %}{% endblock %}</body></html>', encoding='utf-8')
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
        telegram_id = db.Column(db.String(32))
        role = db.Column(db.String(16), default='student')
        is_guest = db.Column(db.Boolean, default=False)
        admin = db.Column(db.Boolean, default=False)

        @property
        def is_admin(self):
            return bool(self.admin)

    fake_models = types.ModuleType('models')
    fake_models.db = db
    fake_models.User = User
    monkeypatch.setitem(sys.modules, 'models', fake_models)

    lm = LoginManager(app)

    @lm.user_loader
    def load(uid):
        return db.session.get(User, int(uid))

    with app.app_context():
        db.create_all()
        db.session.execute(db.text(
            'CREATE TABLE IF NOT EXISTS site_time_sections (user_id INTEGER, section VARCHAR(24), day DATE, seconds INTEGER)'))
        db.session.commit()

    # имитация intake и daily_tasks
    intake = Blueprint('intake', __name__, url_prefix='/intake')

    @intake.route('/answer', methods=['POST'])
    def answer_intake():
        return jsonify({'done': True, 'result': {'anchors_correct': 3, 'daily_tasks': 5}})

    @intake.route('/start', methods=['POST'])
    def start_intake():
        return jsonify({'done': True, 'result': {'anchors_correct': 3}})

    daily = Blueprint('daily_tasks', __name__, url_prefix='/daily_tasks')

    @daily.route('/<int:item_id>/submit', methods=['POST'])
    def submit(item_id):
        return jsonify({'is_correct': True, 'xp': 10})

    @app.route('/login/<int:uid>')
    def do_login(uid):
        u = db.session.get(User, uid)
        login_user(u)
        return 'ok'

    @app.route('/page')
    def page():
        return '<html><body>hi</body></html>'

    app.register_blueprint(intake)
    app.register_blueprint(daily)

    from services import funnel
    funnel._tables_ready = False
    funnel.install(app)
    from routes import admin_stats
    admin_stats.install(app)

    app.User = User
    app.db = db
    return app


def _mk_user(app, admin=False, created=None):
    with app.app_context():
        u = app.User(created_at=created or datetime.utcnow(), admin=admin)
        app.db.session.add(u)
        app.db.session.commit()
        return u.id


def _count(app, event):
    with app.app_context():
        return app.db.session.execute(app.db.text(
            'SELECT COUNT(*) FROM funnel_events WHERE event = :e'), {'e': event}).scalar()


def test_visit_once_per_session_and_track_injected(app):
    c = app.test_client()
    r = c.get('/page?ref=tg')
    assert r.status_code == 200
    assert 'window.track=' in r.get_data(as_text=True)
    c.get('/page')
    assert _count(app, 'visit') == 1
    with app.app_context():
        src = app.db.session.execute(app.db.text("SELECT source FROM funnel_events WHERE event='visit'")).scalar()
    assert src == 'tg'


def test_signup_on_fresh_login_only(app):
    fresh = _mk_user(app)
    old = _mk_user(app, created=datetime.utcnow() - timedelta(days=3))
    c = app.test_client()
    c.get('/page?ref=teacher_7')
    c.get(f'/login/{fresh}')
    assert _count(app, 'signup') == 1
    c.get(f'/login/{fresh}')           # повторный вход — дубль не вставляется
    assert _count(app, 'signup') == 1
    c2 = app.test_client()
    c2.get(f'/login/{old}')
    assert _count(app, 'signup') == 1
    with app.app_context():
        row = app.db.session.execute(app.db.text('SELECT acq_source, acq_ref FROM users WHERE id=:u'), {'u': fresh}).first()
    assert row[0] == 'teacher' and row[1] == 'teacher_7'


def test_intake_done_and_first_task_dedup(app):
    uid = _mk_user(app)
    c = app.test_client()
    c.get(f'/login/{uid}')
    c.post('/intake/start', json={})          # start НЕ считается завершением
    assert _count(app, 'intake_done') == 0
    c.post('/intake/answer', json={'qid': 'q6', 'key': 'x'})
    c.post('/intake/answer', json={'qid': 'q6', 'key': 'x'})
    assert _count(app, 'intake_done') == 1
    c.post('/daily_tasks/1/submit', json={'answer': '42'})
    c.post('/daily_tasks/2/submit', json={'answer': '42'})
    assert _count(app, 'first_task_solved') == 1


def test_api_ev_whitelist_and_auth(app):
    c = app.test_client()
    assert c.post('/api/ev', json={'event': 'limit_hit'}).status_code == 401
    uid = _mk_user(app)
    c.get(f'/login/{uid}')
    assert c.post('/api/ev', json={'event': 'limit_hit', 'props': {'n': 4}}).status_code == 200
    assert c.post('/api/ev', json={'event': 'payment_success'}).status_code == 400
    assert _count(app, 'limit_hit') == 1
    assert _count(app, 'payment_success') == 0


def test_payment_success_idempotent(app):
    uid = _mk_user(app)
    with app.test_request_context('/'):
        from services.funnel import payment_success
        assert payment_success(uid, 'student_year', 2790, payment_id='p1') is True
        assert payment_success(uid, 'student_year', 2790, payment_id='p1') is False
    assert _count(app, 'payment_success') == 1


def test_classify_source(app):
    from services.funnel import classify_source
    with app.test_request_context('/', base_url='https://formyla.net'):
        assert classify_source('tg', None, None) == 'tg'
        assert classify_source('u_15', None, None) == 'referral'
        assert classify_source(None, {'utm_source': 'vk'}, None) == 'social'
        assert classify_source(None, None, 'https://yandex.ru/search/?text=x') == 'organic'
        assert classify_source(None, None, 'https://formyla.net/about') == 'internal'
        assert classify_source(None, None, None) == 'direct_visit'


def test_admin_stats_access_and_registry(app):
    from routes.admin_stats import SECTIONS, GROUP_ORDER
    slugs = {s['slug'] for s in SECTIONS}
    for must in ('overview', 'funnel', 'sources', 'limits', 'subscriptions', 'founders', 'trial',
                 'payments', 'cohorts', 'env_flags', 'users', 'sections', 'returns', 'daily_tasks'):
        assert must in slugs
    assert {s['group'] for s in SECTIONS} <= set(GROUP_ORDER)

    plain = _mk_user(app)
    admin = _mk_user(app, admin=True)
    c = app.test_client()
    assert c.get('/admin/stats/overview').status_code in (302, 401, 403)
    c.get(f'/login/{plain}')
    assert c.get('/admin/stats/overview').status_code == 403
    c2 = app.test_client()
    c2.get(f'/login/{admin}')
    assert c2.get('/admin/stats/').status_code == 302
    for s in SECTIONS:   # все разделы отдают 200, даже если таблиц ещё нет (fail-open)
        r = c2.get(f"/admin/stats/{s['slug']}?p=30")
        assert r.status_code == 200, s['slug']
    r = c2.get('/admin/stats/funnel?p=7&csv=1')
    assert r.status_code == 200 and r.mimetype == 'text/csv'
    assert c2.get('/admin/stats/nope').status_code == 404


def test_block_sections_with_data(app):
    """Платежи/когорты/лимиты считают цифры из funnel_events."""
    admin = _mk_user(app, admin=True)
    uid = _mk_user(app)
    c = app.test_client()
    c.get(f'/login/{uid}')
    c.post('/api/ev', json={'event': 'limit_hit', 'props': {'kind': 'task', 'ab': 1}})
    c.post('/api/ev', json={'event': 'paywall_view', 'props': {'from': 'limit'}})
    with app.test_request_context('/'):
        from services.funnel import payment_success
        assert payment_success(uid, 'student_year', 2790, payment_id='pay-1')
    from routes import admin_stats_sections as sec
    from datetime import date
    today = (datetime.utcnow() + timedelta(hours=3)).date()
    with app.test_request_context('/admin/stats/payments'):
        blocks = sec.payments(today - timedelta(days=7), today)
        cards = [b for b in blocks if b['type'] == 'cards'][0]['items']
        assert cards[0]['value'] == 1 and cards[1]['value'].replace(' ', '') == '2790'
        lim = sec.limits(today - timedelta(days=7), today)
        assert lim[0]['items'][0]['value'] == 1
        pw = sec.paywall(today - timedelta(days=7), today)
        assert pw[0]['items'][0]['value'] == 1
        coh = sec.cohorts(today - timedelta(days=7), today)
        assert coh[0]['type'] == 'table' and len(coh[0]['rows']) >= 1
        for name, fn in sec.VIEWS.items():
            out = fn(today - timedelta(days=7), today)
            assert isinstance(out, list) and out, name
