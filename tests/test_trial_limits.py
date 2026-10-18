# -*- coding: utf-8 -*-
"""TRIAL_V1 + SOFT_LIMITS_V1 + PARENT_OFFER_V1 — тесты на мини-приложении (SQLite).

Запуск: pytest tests/test_trial_limits.py -q
"""
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['ADMIN_BASE_AUTOREG'] = '0'
os.environ['FUNNEL_ENABLED'] = '1'
os.environ['TRIAL_ENABLED'] = '1'
os.environ['TRIAL_DAYS'] = '14'
os.environ['SOFT_LIMITS_ENABLED'] = '1'
os.environ['PAYWALL_ENABLED'] = '1'
os.environ['PAYWALL_START_DATE'] = '2026-01-01'
os.environ['PAYWALL_AB'] = '100'
os.environ['FREE_TASKS_PER_DAY'] = '3'
os.environ['FREE_AI_PER_DAY'] = '1'
os.environ['BILLING_FOUNDER_CUTOFF'] = '2026-01-01'   # в тестах «сейчас» никто не Основатель по дате


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from flask import Flask, Blueprint, jsonify, render_template_string
    from flask_login import LoginManager, UserMixin, login_user, login_required
    from flask_sqlalchemy import SQLAlchemy
    import types, shutil

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tpl = tmp_path / 'templates'
    for sub in ('partials', 'billing', 'parent'):
        (tpl / sub).mkdir(parents=True)
    (tpl / 'base.html').write_text('<html><body>{% block content %}{% endblock %}</body></html>', encoding='utf-8')
    for sub, names in (('partials', ['limit_reached.html']), ('billing', ['limit.html']), ('parent', ['offer.html'])):
        for n in names:
            shutil.copy(os.path.join(root, 'templates', sub, n), tpl / sub / n)

    app = Flask(__name__, template_folder=str(tpl))
    app.config.update(SECRET_KEY='t', TESTING=True, SERVER_NAME='localhost',
                      SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path/'t.db'}", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db = SQLAlchemy(app)

    class User(UserMixin, db.Model):
        __tablename__ = 'users'
        id = db.Column(db.Integer, primary_key=True)
        email = db.Column(db.String(120))
        telegram_id = db.Column(db.String(32))
        name = db.Column(db.String(80))
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
        for ddl in (
            """CREATE TABLE subscriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan TEXT DEFAULT 'free',
               status TEXT DEFAULT 'active', started_at TIMESTAMP, expires_at TIMESTAMP, payment_method TEXT, payment_id TEXT,
               amount_rub INTEGER, is_trial INTEGER DEFAULT 0, is_beta_access INTEGER DEFAULT 1, created_at TIMESTAMP)""",
            """CREATE TABLE usage_daily (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, date DATE,
               tasks_completed INTEGER DEFAULT 0, ai_explanations_used INTEGER DEFAULT 0, tokens_consumed INTEGER DEFAULT 0,
               cost_usd REAL DEFAULT 0, UNIQUE(user_id, date))""",
            "CREATE TABLE daily_task_sets (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, target_date DATE)",
            """CREATE TABLE daily_task_items (id INTEGER PRIMARY KEY AUTOINCREMENT, daily_set_id INTEGER, position INTEGER,
               answered_at TIMESTAMP, is_correct BOOLEAN, debt_status TEXT)""",
            "CREATE TABLE streak_records (user_id INTEGER, current_streak INTEGER, max_streak INTEGER)",
        ):
            db.session.execute(db.text(ddl))
        # занимаем id=1 — в paywall он считается админом и не лимитируется
        db.session.add(User(email='admin@formyla.net', created_at=datetime(2025, 1, 1)))
        db.session.commit()

    daily = Blueprint('daily_tasks', __name__, url_prefix='/daily_tasks')

    @daily.route('/', methods=['GET'])
    @login_required
    def dash():
        return 'dash'

    @daily.route('/<int:item_id>', methods=['GET'])
    @login_required
    def task_page(item_id):
        return f'task {item_id}'

    @daily.route('/<int:item_id>/submit', methods=['POST'])
    @login_required
    def submit(item_id):
        db.session.execute(db.text("UPDATE daily_task_items SET answered_at=:t, is_correct=1 WHERE id=:i"),
                           {'t': datetime.utcnow(), 'i': item_id})
        db.session.commit()
        return jsonify({'is_correct': True})

    tutor = Blueprint('olymp_catalog', __name__)

    @tutor.route('/api/tutor/chat', methods=['POST'])
    @login_required
    def chat():
        return jsonify({'answer': 'ok'})

    @app.route('/login/<int:uid>')
    def do_login(uid):
        login_user(db.session.get(User, uid)); return 'ok'

    @app.route('/page')
    @login_required
    def page():
        return render_template_string('<html><body>hi {{ trial_info.label }}</body></html>')

    app.register_blueprint(daily); app.register_blueprint(tutor)
    from services import funnel, trial, soft_limits
    funnel._tables_ready = False; trial._ready = False
    funnel.install(app); trial.install(app); soft_limits.install(app)
    from routes import parent_offer
    parent_offer.install(app)
    app.User, app.db = User, db
    return app


def _user(app, created=None, email=None, tg=None):
    with app.app_context():
        u = app.User(email=email, telegram_id=tg, created_at=created or datetime.utcnow(), name='Петя')
        app.db.session.add(u); app.db.session.commit(); return u.id


def _items(app, uid, n):
    with app.app_context():
        app.db.session.execute(app.db.text("INSERT INTO daily_task_sets (id, user_id, target_date) VALUES (:s, :u, DATE('now'))"), {'s': uid * 100, 'u': uid})
        for i in range(1, n + 1):
            app.db.session.execute(app.db.text("INSERT INTO daily_task_items (id, daily_set_id, position) VALUES (:i, :s, :p)"),
                                   {'i': uid * 100 + i, 's': uid * 100, 'p': i})
        app.db.session.commit()
    return [uid * 100 + i for i in range(1, n + 1)]


def _no_trial(app, uid):
    with app.app_context():
        app.db.session.execute(app.db.text("UPDATE users SET trial_until=NULL WHERE id=:u"), {'u': uid}); app.db.session.commit()


def _trial_until(app, uid):
    with app.app_context():
        return app.db.session.execute(app.db.text('SELECT trial_until FROM users WHERE id=:u'), {'u': uid}).scalar()


# ───────────── TRIAL ─────────────
def test_trial_granted_once_per_email_and_not_for_founder(app):
    new1 = _user(app, email='kid@example.com')          # создан сейчас → свежий
    c = app.test_client(); c.get(f'/login/{new1}')
    assert _trial_until(app, new1) is not None
    new2 = _user(app, email='KID@example.com')          # тот же e-mail — триала нет
    c2 = app.test_client(); c2.get(f'/login/{new2}')
    assert _trial_until(app, new2) is None
    founder = _user(app, created=datetime(2025, 12, 1), email='old@example.com')   # до отсечки → Основатель
    with app.app_context():
        u = app.db.session.get(app.User, founder)
        from services.trial import is_trial_active, trial_info, grant_trial
        assert grant_trial(u) is False
        assert is_trial_active(u) is True and trial_info(u)['kind'] == 'founder'
        assert hasattr(app.User, 'is_trial_active') and u.is_trial_active() is True
    html = c.get('/page').get_data(as_text=True)
    assert 'Premium до' in html and 'ft-plan-badge' in html


def test_trial_expired(app):
    uid = _user(app, created=datetime(2026, 2, 3), email='x@example.com')
    with app.app_context():
        app.db.session.execute(app.db.text("UPDATE users SET trial_until=:t WHERE id=:u"),
                               {'t': datetime.utcnow() - timedelta(days=1), 'u': uid}); app.db.session.commit()
        from services.trial import is_trial_active
        assert is_trial_active(app.db.session.get(app.User, uid)) is False


# ───────────── SOFT LIMITS ─────────────
def test_free_user_limited_after_3_tasks_but_dashboard_open(app):
    uid = _user(app, created=datetime(2026, 2, 3), email='free@example.com')   # не свежий → без триала
    items = _items(app, uid, 5)
    c = app.test_client(); c.get(f'/login/{uid}'); _no_trial(app, uid)
    for i in items[:3]:
        assert c.post(f'/daily_tasks/{i}/submit', json={'answer': '1'}).status_code == 200
    r = c.post(f'/daily_tasks/{items[3]}/submit', json={'answer': '1'})
    assert r.status_code == 402
    j = r.get_json()
    assert j['error'] == 'limit' and j['upgrade_url'] == '/subscribe?from=daily_limit' and 'Отправить родителю' in j['html']
    assert c.get('/daily_tasks/').status_code == 200                       # дашборд не блокируется
    page = c.get(f'/daily_tasks/{items[4]}')
    assert page.status_code == 200 and 'серия сохранена' in page.get_data(as_text=True)
    assert c.get(f'/daily_tasks/{items[0]}').get_data(as_text=True) == f'task {items[0]}'   # отвеченную можно смотреть
    with app.app_context():
        n = app.db.session.execute(app.db.text("SELECT COUNT(*) FROM funnel_events WHERE event='limit_hit'")).scalar()
    assert n >= 1


def test_debt_task_not_counted_and_not_blocked(app):
    uid = _user(app, created=datetime(2026, 2, 3), email='debt@example.com')
    items = _items(app, uid, 5)
    c = app.test_client(); c.get(f'/login/{uid}'); _no_trial(app, uid)
    with app.app_context():
        app.db.session.execute(app.db.text("UPDATE daily_task_items SET debt_status='active' WHERE id=:i"), {'i': items[4]})
        app.db.session.commit()
    for i in items[:3]:
        c.post(f'/daily_tasks/{i}/submit', json={'answer': '1'})
    assert c.post(f'/daily_tasks/{items[4]}/submit', json={'answer': '1'}).status_code == 200   # долг — без лимита
    assert c.post(f'/daily_tasks/{items[3]}/submit', json={'answer': '1'}).status_code == 402


def test_trial_user_and_control_cohort_not_limited(app, monkeypatch):
    uid = _user(app, email='trial@example.com')                 # свежий → триал при входе → лимитов нет
    items = _items(app, uid, 5)
    c = app.test_client(); c.get(f'/login/{uid}')
    for i in items[:4]:
        assert c.post(f'/daily_tasks/{i}/submit', json={'answer': '1'}).status_code == 200
    uid2 = _user(app, created=datetime(2026, 2, 3), email='ctrl@example.com')
    items2 = _items(app, uid2, 5)
    c2 = app.test_client(); c2.get(f'/login/{uid2}'); _no_trial(app, uid2)
    monkeypatch.setenv('PAYWALL_AB', '0')                        # контрольная когорта
    for i in items2[:4]:
        assert c2.post(f'/daily_tasks/{i}/submit', json={'answer': '1'}).status_code == 200


def test_ai_limit_one_per_day(app):
    uid = _user(app, created=datetime(2026, 2, 3), email='ai@example.com')
    c = app.test_client(); c.get(f'/login/{uid}'); _no_trial(app, uid)
    assert c.post('/api/tutor/chat', json={'q': 'x'}).status_code == 200
    r = c.post('/api/tutor/chat', json={'q': 'y'})
    assert r.status_code == 402 and r.get_json()['kind'] == 'ai'


def test_streak_rule_and_ab():
    from services.soft_limits import streak_required
    from services.ab import cohort_of
    assert streak_required(3) == 2 and streak_required(5) == 4
    os.environ['PAYWALL_AB'] = '50'
    assert cohort_of(10) == 1 and cohort_of(60) == 0
    os.environ['PAYWALL_AB'] = '100'


# ───────────── PARENT OFFER ─────────────
def test_parent_offer_link_and_page(app):
    uid = _user(app, created=datetime(2026, 2, 3), email='p@example.com')
    c = app.test_client(); c.get(f'/login/{uid}')
    r = c.post('/parent/offer-link', json={'from': 'limit'})
    d = r.get_json()
    assert d['ok'] and '/parent/offer/' in d['url'] and d['tg'].startswith('https://t.me/share')
    anon = app.test_client()
    page = anon.get(f"/parent/offer/{d['token']}")
    assert page.status_code == 200 and 'Premium' in page.get_data(as_text=True)
    assert anon.get('/parent/offer/bad-token').status_code == 404
