# -*- coding: utf-8 -*-
"""Раздел «Подписки» и журнал просмотров (page_views) / «Где уходят».

Запуск: pytest tests/test_stats_subscriptions_pageviews.py -q
Мини-приложение Flask + SQLite, production-модели не трогаются.
"""
import os
import shutil
import sys
import types
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['ADMIN_BASE_AUTOREG'] = '0'


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from flask import Flask
    from flask_login import LoginManager, UserMixin, login_user
    from flask_sqlalchemy import SQLAlchemy

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
        nickname = db.Column(db.String(50))
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        trial_until = db.Column(db.DateTime)
        is_guest = db.Column(db.Boolean, default=False)
        admin = db.Column(db.Boolean, default=False)

        @property
        def is_admin(self):
            return bool(self.admin)

    fake = types.ModuleType('models')
    fake.db, fake.User = db, User
    monkeypatch.setitem(sys.modules, 'models', fake)

    lm = LoginManager(app)

    @lm.user_loader
    def load(uid):
        return db.session.get(User, int(uid))

    with app.app_context():
        db.create_all()
        db.session.execute(db.text(
            """CREATE TABLE subscriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan TEXT,
               status TEXT, started_at DATETIME, expires_at DATETIME, payment_id TEXT, amount_rub INTEGER,
               is_beta_access BOOLEAN DEFAULT 0, is_trial BOOLEAN DEFAULT 0, created_at DATETIME)"""))
        db.session.commit()

    @app.route('/login/<int:uid>')
    def do_login(uid):
        login_user(db.session.get(User, uid))
        return 'ok'

    @app.route('/problems/<int:pid>')
    def problem(pid):
        return '<html><body>p</body></html>'

    @app.route('/api/x')
    def api_x():
        return '<html></html>'

    from services import page_views
    page_views._tables_ready = False
    page_views.install(app)
    from routes import admin_stats
    admin_stats.install(app)
    # user_returns мог быть импортирован раньше с настоящим models.db
    try:
        import services.user_returns as _ur
        monkeypatch.setattr(_ur, 'db', db)
    except Exception:
        pass
    app.User, app.db = User, db
    return app


def _user(app, nick, admin=False, trial_until=None):
    with app.app_context():
        u = app.User(nickname=nick, admin=admin, trial_until=trial_until)
        app.db.session.add(u)
        app.db.session.commit()
        return u.id


def _sub(app, uid, plan, days_left, status='active', amount=0, pay='p', beta=0, trial=0):
    now = datetime.utcnow()
    with app.app_context():
        app.db.session.execute(app.db.text(
            'INSERT INTO subscriptions (user_id, plan, status, started_at, expires_at, payment_id, amount_rub, '
            'is_beta_access, is_trial, created_at) VALUES (:u,:p,:s,:st,:ex,:pay,:a,:b,:t,:c)'),
            {'u': uid, 'p': plan, 's': status, 'st': now - timedelta(days=5), 'ex': now + timedelta(days=days_left),
             'pay': pay if amount else None, 'a': amount, 'b': beta, 't': trial, 'c': now - timedelta(days=5)})
        app.db.session.commit()


def _admin_client(app):
    aid = _user(app, 'boss', admin=True)
    c = app.test_client()
    c.get(f'/login/{aid}')
    return c


# ───────────── page_views ─────────────
def test_normalize_path():
    from services.page_views import normalize_path
    assert normalize_path('/problems/123?x=1') == '/problems/<id>'
    assert normalize_path('/intake/') == '/intake'
    assert normalize_path('/') == '/'
    assert normalize_path('/t/' + 'z' * 40) == '/t/' + 'z' * 40  # обычный длинный слаг не трогаем
    assert normalize_path('/s/0123456789abcdef0123456789abcdef') == '/s/<id>'


def test_hook_records_user_views_only_for_pages(app):
    uid = _user(app, 'kid')
    c = app.test_client()
    c.get(f'/login/{uid}')
    c.get('/problems/7')
    c.get('/problems/7')          # дубль в пределах 3 секунд
    c.get('/problems/8')
    c.get('/api/x')               # не пишем
    with app.app_context():
        rows = app.db.session.execute(app.db.text('SELECT user_id, path FROM page_views')).fetchall()
    assert [(r[0], r[1]) for r in rows] == [(uid, '/problems/<id>'), (uid, '/problems/<id>')]


def test_admin_views_not_recorded(app):
    c = _admin_client(app)
    c.get('/problems/1')
    with app.app_context():
        n = app.db.session.execute(app.db.text('SELECT COUNT(*) FROM page_views')).scalar()
    assert n == 0


def test_analyze_exits_bounce_and_intake():
    from services.page_views import analyze
    t = datetime(2026, 11, 1, 10, 0)
    m = lambda k: t + timedelta(minutes=k)
    rows = [
        (1, None, '/', m(0)), (1, None, '/intake', m(1)), (1, None, '/intake', m(2)),   # бросил анкету
        (2, None, '/', m(0)), (2, None, '/intake', m(1)), (2, None, '/prep/coach', m(3)),  # прошёл
        (3, None, '/', m(0)),                                                              # отскок
        (1, None, '/', m(200)),                                                            # новый визит
    ]
    a = analyze(rows)
    assert a['visits'] == 4 and a['people'] == 3 and a['views'] == 8
    assert a['exits']['/intake'] == 1 and a['exits']['/prep/coach'] == 1 and a['exits']['/'] == 2
    assert a['bounces']['/'] == 2           # user3 и второй визит user1
    assert a['intake_visits'] == 2 and a['intake_left_inside'] == 1


def test_exit_pages_section_renders(app):
    c = _admin_client(app)
    uid = _user(app, 'kid')
    now = datetime.utcnow()
    with app.app_context():
        for i, p in enumerate(['/', '/intake', '/intake']):
            app.db.session.execute(app.db.text('INSERT INTO page_views (user_id, path, created_at) VALUES (:u,:p,:t)'),
                                   {'u': uid, 'p': p, 't': now - timedelta(minutes=10 - i)})
        app.db.session.commit()
    r = c.get('/admin/stats/exit_pages?p=today')
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'Страницы выхода' in html and '/intake' in html
    assert 'Визиты с анкетой' in html


# ───────────── подписки ─────────────
def test_subscriptions_table_titles_mrr_and_filters(app):
    a = _user(app, 'worker')
    b = _user(app, 'calm')
    c_ = _user(app, 'zexpired')
    d = _user(app, 'zstopped')
    _sub(app, a, 'premium_intense', 20, amount=800)
    _sub(app, b, 'premium_calm', 3, amount=500)          # истекает
    _sub(app, c_, 'premium_calm', -2, amount=500)        # истекла
    _sub(app, d, 'premium_monthly', 10, status='cancelled', amount=390)
    c = _admin_client(app)
    html = c.get('/admin/stats/subscriptions?p=30').get_data(as_text=True)
    assert 'Работяга' in html and 'Спокойный' in html
    assert 'worker' in html and 'calm' in html
    assert 'zexpired' not in html and 'zstopped' not in html     # активные по умолчанию
    assert '1 300' in html                                   # MRR 800 + 500
    assert 'zexpired' in c.get('/admin/stats/subscriptions?f=expired&p=30').get_data(as_text=True)
    assert 'zstopped' in c.get('/admin/stats/subscriptions?f=cancelled&p=30').get_data(as_text=True)
    exp = c.get('/admin/stats/subscriptions?f=expiring&p=30').get_data(as_text=True)
    assert 'calm' in exp and 'worker' not in exp


def test_subscriptions_search_and_csv(app):
    a = _user(app, 'alpha')
    b = _user(app, 'beta')
    _sub(app, a, 'premium_intense', 20, amount=800)
    _sub(app, b, 'premium_yearly', 100, amount=2790)
    c = _admin_client(app)
    html = c.get('/admin/stats/subscriptions?q=alp&p=30').get_data(as_text=True)
    assert 'alpha' in html and 'beta' not in html.split('<tbody>')[1]
    r = c.get('/admin/stats/subscriptions?f=all&csv=1&p=30')
    text = r.get_data(as_text=True)
    assert r.mimetype == 'text/csv' and 'alpha' in text and 'beta' in text


def test_subscriptions_trial_from_users_field(app):
    uid = _user(app, 'trialist', trial_until=datetime.utcnow() + timedelta(days=5))
    c = _admin_client(app)
    html = c.get('/admin/stats/subscriptions?p=30').get_data(as_text=True)
    assert 'trialist' in html and 'Триал' in html


def test_subscriptions_requires_admin(app):
    uid = _user(app, 'kid')
    c = app.test_client()
    c.get(f'/login/{uid}')
    assert c.get('/admin/stats/subscriptions').status_code == 403


# ───────────── путь регистрации, опросы, ушедшие, сводка ─────────────
def _prep_journey_tables(app):
    with app.app_context():
        for sql in (
            "CREATE TABLE IF NOT EXISTS readiness_survey_answers (user_id INTEGER PRIMARY KEY, answer VARCHAR(16), answered_at DATETIME)",
            "CREATE TABLE IF NOT EXISTS site_feedback (user_id INTEGER, rating INTEGER, feedback_text TEXT, answered_at DATETIME)",
            "CREATE TABLE IF NOT EXISTS site_time_sections (user_id INTEGER, section VARCHAR(24), day DATE, seconds INTEGER)",
            "CREATE TABLE IF NOT EXISTS site_time_beat (user_id INTEGER PRIMARY KEY, last_beat DATETIME, last_section VARCHAR(24), last_page VARCHAR(160))",
        ):
            app.db.session.execute(app.db.text(sql))
        app.db.session.commit()
    from services import funnel
    funnel._tables_ready = False
    with app.app_context():
        funnel.ensure_tables()


def _event(app, uid, event, props=None, ago_min=60):
    import json
    with app.app_context():
        app.db.session.execute(app.db.text(
            'INSERT INTO funnel_events (user_id, event, props, created_at) VALUES (:u,:e,:p,:t)'),
            {'u': uid, 'e': event, 'p': json.dumps(props) if props else None,
             't': datetime.utcnow() - timedelta(minutes=ago_min)})
        app.db.session.commit()


def _activity(app, uid, day, sec=100):
    with app.app_context():
        app.db.session.execute(app.db.text(
            "INSERT INTO site_time_sections (user_id, section, day, seconds) VALUES (:u,'general',:d,:s)"),
            {'u': uid, 'd': day, 's': sec})
        app.db.session.commit()


def test_journey_steps_stuck_and_intake_questions(app):
    _prep_journey_tables(app)
    a, b, c_ = _user(app, 'done'), _user(app, 'quit'), _user(app, 'idle')
    _event(app, a, 'intake_answer', {'qid': 'goal'})
    _event(app, a, 'intake_done')
    _event(app, a, 'first_task_solved')
    _event(app, b, 'intake_answer', {'qid': 'goal'}, ago_min=30)
    _event(app, b, 'intake_answer', {'qid': 'grade'}, ago_min=20)
    cl = _admin_client(app)
    html = cl.get('/admin/stats/journey?p=today').get_data(as_text=True)
    assert 'Путь когорты' in html and 'Прошли анкету' in html
    assert 'Где бросают анкету' in html and '>grade<' in html     # b остановился на grade
    stuck = cl.get('/admin/stats/journey?p=today&stop=intake_start').get_data(as_text=True)
    assert 'quit' in stuck and 'done' not in stuck.split('Остановились на шаге')[1]


def test_survey_behavior_groups(app):
    _prep_journey_tables(app)
    a, b = _user(app, 'ready'), _user(app, 'notready')
    ans_day = datetime.utcnow() - timedelta(days=10)
    with app.app_context():
        for uid, ans in ((a, 'yes'), (b, 'not_yet')):
            app.db.session.execute(app.db.text('INSERT INTO readiness_survey_answers VALUES (:u,:a,:t)'),
                                   {'u': uid, 'a': ans, 't': ans_day})
        app.db.session.commit()
    _activity(app, a, (ans_day + timedelta(days=2)).date())      # a вернулся
    _event(app, a, 'first_task_solved')
    cl = _admin_client(app)
    html = cl.get('/admin/stats/survey_behavior?p=30').get_data(as_text=True)
    assert 'Готов заниматься каждый день' in html and 'Пока не готов' in html
    assert '1 из 1 (100.0%)' in html and '0 из 1 (0.0%)' in html


def test_lost_users_last_page(app):
    _prep_journey_tables(app)
    a, b = _user(app, 'gone1'), _user(app, 'active1')
    old = (datetime.utcnow() - timedelta(days=9)).date()
    _activity(app, a, old)
    _activity(app, b, datetime.utcnow().date())
    with app.app_context():
        app.db.session.execute(app.db.text("INSERT INTO site_time_beat (user_id, last_beat, last_page) VALUES (:u,:t,'/intake?x=1')"),
                               {'u': a, 't': datetime.utcnow() - timedelta(days=9)})
        app.db.session.commit()
    cl = _admin_client(app)
    html = cl.get('/admin/stats/lost_users').get_data(as_text=True)
    assert 'gone1' in html and 'active1' not in html and '/intake' in html
    assert 'gone1' not in cl.get('/admin/stats/lost_users?days=14').get_data(as_text=True)


def test_overview_shows_previous_period_delta(app):
    _prep_journey_tables(app)
    u = _user(app, 'x')
    _event(app, u, 'signup', ago_min=60)
    cl = _admin_client(app)
    r = cl.get('/admin/stats/overview?p=7')
    assert r.status_code == 200 and 'было' in r.get_data(as_text=True)


def test_overview_sparkline_and_collapsed_menu(app):
    _prep_journey_tables(app)
    u = _user(app, 'x')
    _event(app, u, 'signup', ago_min=60)
    _event(app, _user(app, 'y'), 'signup', ago_min=60 * 30)
    cl = _admin_client(app)
    html = cl.get('/admin/stats/overview?p=7').get_data(as_text=True)
    assert '<polyline' in html
    assert 'class="st-nav-group">' in html          # «Продукт» и «Система» свёрнуты
    assert 'class="st-nav-group" open>' in html     # остальные раскрыты
    # в свёрнутой группе раздел открывается раскрытым
    html = cl.get('/admin/stats/ai_usage').get_data(as_text=True)
    assert html.count('class="st-nav-group">') == 1


def test_spark_helper():
    from routes.admin_stats import _spark
    assert _spark([0, 0, 0]) is None and _spark([5]) is None
    pts = _spark([0, 5, 10])
    assert len(pts.split()) == 3 and pts.split()[0].startswith('0.0,')


# ───────────── бывшие встроенные страницы: теперь разделы с периодом ─────────────
def _reset_returns_cache():
    from services import user_returns
    user_returns._cache.update(ts=0, events=None, sources=None)


def test_users_section_period_csv_and_activity(app):
    _prep_journey_tables(app)
    with app.app_context():
        for col, typ in (('last_login', 'DATETIME'), ('login_count', 'INTEGER'),
                         ('experience_points', 'INTEGER'), ('site_seconds_total', 'INTEGER')):
            app.db.session.execute(app.db.text(f'ALTER TABLE users ADD COLUMN {col} {typ}'))
        app.db.session.commit()
    kid = _user(app, 'newbie')
    with app.app_context():
        app.db.session.execute(app.db.text('UPDATE users SET experience_points = 77, site_seconds_total = 600 WHERE id = :i'), {'i': kid})
        app.db.session.execute(app.db.text('INSERT INTO page_views (user_id, path, created_at) VALUES (:u, :p, :t)'),
                               {'u': kid, 'p': '/', 't': datetime.utcnow()})
        app.db.session.commit()
    _reset_returns_cache()
    cl = _admin_client(app)
    r = cl.get('/admin/stats/users?p=7')
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'newbie' in html and 'Топ-10 по XP' in html and 'Средний DAU' in html
    assert '<iframe' not in html
    old = cl.get('/admin/stats/users?p=custom&from=2020-01-01&to=2020-01-02').get_data(as_text=True)
    assert 'newbie' not in old.split('Зарегистрировались за период (')[1]
    csv = cl.get('/admin/stats/users?p=7&csv=1')
    assert csv.mimetype == 'text/csv' and 'newbie' in csv.get_data(as_text=True)


def test_returns_section_counts_second_visit(app):
    _prep_journey_tables(app)
    kid, other = _user(app, 'back'), _user(app, 'once')
    now = datetime.utcnow()
    with app.app_context():
        for uid, mins in ((kid, 300), (kid, 10), (other, 20)):   # у kid два визита с паузой > 60 мин
            app.db.session.execute(app.db.text('INSERT INTO page_views (user_id, path, created_at) VALUES (:u,:p,:t)'),
                                   {'u': uid, 'p': '/', 't': now - timedelta(minutes=mins)})
        app.db.session.commit()
    _reset_returns_cache()
    cl = _admin_client(app)
    html = cl.get('/admin/stats/returns?p=7').get_data(as_text=True)
    assert 'вернулись 2-й раз' in html and 'Вернулись хотя бы раз' in html and 'back' in html
    assert '<iframe' not in html


def test_surveys_section_period_filter(app):
    _prep_journey_tables(app)
    a, b = _user(app, 'rater'), _user(app, 'oldrater')
    now = datetime.utcnow()
    with app.app_context():
        app.db.session.execute(app.db.text("INSERT INTO site_feedback VALUES (:u, 5, 'супер', :t)"), {'u': a, 't': now})
        app.db.session.execute(app.db.text("INSERT INTO site_feedback VALUES (:u, 1, 'плохо', :t)"), {'u': b, 't': now - timedelta(days=60)})
        app.db.session.execute(app.db.text("INSERT INTO readiness_survey_answers VALUES (:u, 'yes', :t)"), {'u': a, 't': now})
        app.db.session.commit()
    cl = _admin_client(app)
    html = cl.get('/admin/stats/surveys?p=7').get_data(as_text=True)
    assert 'rater' in html and 'супер' in html and 'плохо' not in html
    assert 'Да, готов!' in html
    assert 'плохо' in cl.get(f'/admin/stats/surveys?p=custom&from={(datetime.utcnow() - timedelta(days=90)).date()}&to={datetime.utcnow().date()}').get_data(as_text=True)


# ───────────── точечное отслеживание: причины ухода, путь человека, оплата ─────────────
def _yk_table(app):
    with app.app_context():
        app.db.session.execute(app.db.text(
            "CREATE TABLE IF NOT EXISTS yookassa_payments (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id VARCHAR(64), "
            "payment_id VARCHAR(128), user_id INTEGER, item_code VARCHAR(64), amount_rub NUMERIC, status VARCHAR(32), "
            "confirmation_url TEXT, created_at TIMESTAMP, paid_at TIMESTAMP)"))
        app.db.session.commit()


def _pay_try(app, uid, status='canceled', ago_min=30):
    with app.app_context():
        app.db.session.execute(app.db.text(
            "INSERT INTO yookassa_payments (order_id, user_id, item_code, amount_rub, status, created_at) "
            "VALUES (:o, :u, 'premium_calm', 500, :s, :t)"),
            {'o': f'o{uid}{status}', 'u': uid, 's': status, 't': datetime.utcnow() - timedelta(minutes=ago_min)})
        app.db.session.commit()


def test_signals_rules(app):
    _prep_journey_tables(app)
    _yk_table(app)
    a, b, c_, d = _user(app, 'payquit'), _user(app, 'quiz'), _user(app, 'limiter'), _user(app, 'quiet')
    _pay_try(app, a)
    _event(app, b, 'intake_answer', {'qid': 'grade'})
    _event(app, c_, 'limit_shown')
    _event(app, d, 'first_task_solved')
    for day in range(3):
        _activity(app, d, (datetime.utcnow() - timedelta(days=day + 1)).date())
    from routes.admin_stats_person import signals_for, reason_text
    with app.test_request_context():
        sig = signals_for([a, b, c_, d])
    assert sig[a]['primary'] == 'checkout_abandoned'
    assert sig[b]['primary'] == 'intake_quit' and 'grade' in reason_text(sig[b])
    assert sig[c_]['primary'] == 'limit_no_pay'
    assert sig[d]['primary'] == 'unknown'


def test_person_page_timeline_and_reason(app):
    _prep_journey_tables(app)
    _yk_table(app)
    uid = _user(app, 'tracked')
    _event(app, uid, 'intake_answer', {'qid': 'goal'}, ago_min=50)
    _pay_try(app, uid, ago_min=10)
    with app.app_context():
        app.db.session.execute(app.db.text("INSERT INTO page_views (user_id, path, created_at) VALUES (:u, '/subscribe', :t)"),
                               {'u': uid, 't': datetime.utcnow() - timedelta(minutes=20)})
        app.db.session.commit()
    cl = _admin_client(app)
    html = cl.get(f'/admin/stats/person?id={uid}').get_data(as_text=True)
    assert 'tracked' in html and 'Лента действий' in html
    assert '/subscribe' in html and 'вопрос: goal' in html and 'Платёж ЮKassa' in html
    assert 'Вероятная причина: Начал оплату и не оплатил' in html
    by_nick = cl.get('/admin/stats/person?q=track').get_data(as_text=True)
    assert 'Лента действий' in by_nick
    assert 'Введите ID или ник' in cl.get('/admin/stats/person').get_data(as_text=True)


def test_paywall_path_and_abandoned_list(app):
    _prep_journey_tables(app)
    _yk_table(app)
    a, b = _user(app, 'bought'), _user(app, 'dropped')
    _event(app, a, 'limit_shown')
    _event(app, b, 'limit_shown')
    _pay_try(app, a, status='succeeded')
    _pay_try(app, b, status='canceled')
    cl = _admin_client(app)
    html = cl.get('/admin/stats/paywall?p=7').get_data(as_text=True)
    assert 'Путь к оплате' in html and 'Начали оплату и не оплатили' in html
    tail = html.split('Начали оплату и не оплатили</h3>')[1]
    assert 'dropped' in tail and 'bought' not in tail.split('</table>')[0]


def test_limit_shown_counts_as_limit(app):
    _prep_journey_tables(app)
    uid = _user(app, 'lim')
    _event(app, uid, 'limit_shown')
    cl = _admin_client(app)
    html = cl.get('/admin/stats/limits?p=7').get_data(as_text=True)
    assert 'Упёрлись в лимит (уник.)' in html
    assert '<div class="v">1</div>' in html.split('Упёрлись в лимит (уник.)')[1][:200]


def test_guest_views_linked_on_signup_and_bots_skipped(app):
    from services import page_views
    with app.app_context():
        page_views.record_view('/', None, 'anon-1')
        page_views.record_view('/about', None, 'anon-1')
        n = page_views.link_anon_to_user('anon-1', 42)
        rows = app.db.session.execute(app.db.text('SELECT user_id FROM page_views')).fetchall()
    assert n == 2 and all(r[0] == 42 for r in rows)
    c = app.test_client()
    c.get('/problems/1', headers={'User-Agent': 'Mozilla/5.0 (compatible; YandexBot/3.0)'})
    with app.app_context():
        total = app.db.session.execute(app.db.text('SELECT COUNT(*) FROM page_views')).scalar()
    assert total == 2


# ───────────── вопрос «что остановило?» ─────────────
def _install_exit_q(app):
    from services import exit_question
    exit_question._ready_engine = None
    exit_question.install(app)


def _login(app, uid):
    c = app.test_client()
    c.get(f'/login/{uid}')
    return c


def test_exit_question_after_abandoned_checkout(app):
    _install_exit_q(app)
    _prep_journey_tables(app)
    _yk_table(app)
    uid = _user(app, 'payer')
    _pay_try(app, uid, status='canceled', ago_min=40)
    c = _login(app, uid)
    d = c.get('/api/exit-question/pending').get_json()
    assert d['pending'] and d['trigger'] == 'checkout' and 'Что остановило' in d['question']
    assert any(o['value'] == 'expensive' for o in d['options'])
    bad = c.post('/api/exit-question', json={'trigger': 'checkout', 'key': d['key'], 'answer': 'expensive'},
                 headers={'X-Exit-CSRF': 'wrong'})
    assert bad.status_code == 403
    ok = c.post('/api/exit-question', json={'trigger': 'checkout', 'key': d['key'], 'answer': 'expensive', 'text': 'дороговато'},
                headers={'X-Exit-CSRF': d['csrf']})
    assert ok.get_json()['ok'] is True
    assert c.get('/api/exit-question/pending').get_json()['pending'] is False
    cl = _admin_client(app)
    person = cl.get(f'/admin/stats/person?id={uid}').get_data(as_text=True)
    assert 'Сам назвал причину' in person and 'Дорого' in person and 'дороговато' in person
    surveys = cl.get('/admin/stats/surveys?p=7').get_data(as_text=True)
    assert 'что остановило?»: ответы' in surveys and 'Дорого' in surveys


def test_exit_question_comeback_dismiss_and_rules(app):
    _install_exit_q(app)
    _prep_journey_tables(app)
    _yk_table(app)
    uid = _user(app, 'returner')
    _activity(app, uid, (datetime.utcnow() + timedelta(hours=3) - timedelta(days=10)).date())
    c = _login(app, uid)
    d = c.get('/api/exit-question/pending').get_json()
    assert d['trigger'] == 'comeback' and 'не было 10 дн.' in d['question']
    c.post('/api/exit-question', json={'trigger': 'comeback', 'key': d['key'], 'dismiss': True}, headers={'X-Exit-CSRF': d['csrf']})
    from services.exit_question import pending_for
    with app.app_context():
        assert pending_for(uid) is None                                        # пропустил — не спрашиваем
        assert pending_for(uid, datetime.utcnow() + timedelta(days=4)) is None  # тот же перерыв — и позже не спрашиваем
        st = app.db.session.execute(app.db.text('SELECT status FROM exit_answers WHERE user_id = :u'), {'u': uid}).scalar()
    assert st == 'dismissed'
    # оплатил после неудачи — про оплату не спрашиваем
    other = _user(app, 'paidlater')
    _pay_try(app, other, status='canceled', ago_min=90)
    with app.app_context():
        app.db.session.execute(app.db.text(
            "INSERT INTO yookassa_payments (order_id, user_id, item_code, amount_rub, status, created_at) "
            "VALUES ('ok1', :u, 'premium_calm', 500, 'succeeded', :t)"), {'u': other, 't': datetime.utcnow() - timedelta(minutes=60)})
        app.db.session.commit()
        assert pending_for(other) is None


def test_exit_question_script_injection(app):
    _install_exit_q(app)
    uid = _user(app, 'kid')
    html = _login(app, uid).get('/problems/1').get_data(as_text=True)
    assert 'id="ft-exit-q-script"' in html
    admin_html = _admin_client(app).get('/problems/1').get_data(as_text=True)
    assert 'ft-exit-q-script' not in admin_html
