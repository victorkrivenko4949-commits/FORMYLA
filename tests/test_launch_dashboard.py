# -*- coding: utf-8 -*-
"""LAUNCH_V1 — тесты дашборда запуска (промпт 29).

Запуск: pytest tests/test_launch_dashboard.py -q
Все данные синтетические и помечены как тестовые (orders.is_test=1 исключается
из выручки; users — фикстурные).
"""
from datetime import datetime, timedelta, timezone

import pytest

import services.launch_metrics as lm

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def lapp(app, monkeypatch):
    monkeypatch.setenv('ADMIN_LAUNCH_ENABLED', '1')
    monkeypatch.setenv('PAYWALL_MODE', 'experiment')
    monkeypatch.setenv('PAYWALL_EXPERIMENT_ID', 'limits_v1')
    monkeypatch.setenv('LAUNCH_MIN_ELIGIBLE', '150')
    from models import db
    from sqlalchemy import text
    db.create_all()
    pg = db.engine.dialect.name == 'postgresql'
    serial = 'SERIAL PRIMARY KEY' if pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    for ddl in (
        f"""CREATE TABLE IF NOT EXISTS subscriptions (
            id {serial}, user_id INTEGER NOT NULL, plan TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active', started_at TIMESTAMP, expires_at TIMESTAMP,
            payment_method TEXT, payment_id TEXT, amount_rub INTEGER, is_trial INTEGER DEFAULT 0,
            is_beta_access INTEGER DEFAULT 1, created_at TIMESTAMP)""",
        f"""CREATE TABLE IF NOT EXISTS usage_daily (
            id {serial}, user_id INTEGER NOT NULL,
            date TEXT NOT NULL, tasks_completed INTEGER DEFAULT 0,
            ai_explanations_used INTEGER DEFAULT 0, tokens_consumed INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0)""",
        f"""CREATE TABLE IF NOT EXISTS funnel_events (
            id {serial}, user_id INTEGER, anon_id VARCHAR(36),
            event VARCHAR(40) NOT NULL, props JSONB,
            source VARCHAR(40), ref VARCHAR(80), path VARCHAR(200),
            referrer VARCHAR(300), created_at TIMESTAMP)""" if pg else
        """CREATE TABLE IF NOT EXISTS funnel_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, anon_id VARCHAR(36),
            event VARCHAR(40) NOT NULL, props TEXT,
            source VARCHAR(40), ref VARCHAR(80), path VARCHAR(200),
            referrer VARCHAR(300), created_at DATETIME)""",
    ):
        db.session.execute(text(ddl))
    db.session.commit()
    return app


def _mk_user(lapp, email, **kw):
    from models import db, User
    u = User(email=email, is_guest=False, **kw)
    db.session.add(u)
    db.session.commit()
    return u


def _client(lapp, user):
    c = lapp.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id)
    return c


def _mk_admin(lapp):
    """user_id == 1 — админ по is_admin."""
    from models import db, User
    u = User.query.get(1)
    if u is None:
        u = User(email='admin@x.invalid', is_guest=False)
        db.session.add(u)
        db.session.commit()
    return u


def _act(lapp, uid, day, n=2):
    """Активность: ответы на задачи дня (реальный источник, не usage_daily).
    answered_at — та же дата, что target_date (долг может быть закрыт позже)."""
    from models import db
    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    d = datetime.strptime(day, '%Y-%m-%d').date()
    at = datetime(d.year, d.month, d.day, 12)
    s = DailyTaskSet(user_id=uid, target_date=d, status='ready')
    db.session.add(s)
    db.session.flush()
    for i in range(n):
        db.session.add(DailyTaskItem(daily_set_id=s.id, position=i + 1,
                                    task_text='t', user_answer='1',
                                    answered_at=at))
    db.session.commit()


def _ev(lapp, uid, event, day, props=None):
    """Событие funnel_events от пользователя (created_at = день+12:00 UTC)."""
    from models import db
    from sqlalchemy import text
    import json
    d = datetime.strptime(day, '%Y-%m-%d').date()
    db.session.execute(text(
        'INSERT INTO funnel_events (user_id, event, props, source, created_at) '
        'VALUES (:u, :e, :p, :s, :c)'),
        {'u': uid, 'e': event,
         'p': json.dumps(props or {}), 's': 'test',
         'c': datetime(d.year, d.month, d.day, 12)})
    db.session.commit()


def _streak(lapp, uid, day, streak=3, broken=False):
    """События серии: streak_day (props.streak) и опционально streak_broken."""
    _ev(lapp, uid, 'streak_day', day, {'streak': streak})
    if broken:
        _ev(lapp, uid, 'streak_broken', day, {})


def _seed_experiment(lapp, n_limits=200, n_control=200, active_ratio=(0.5, 0.5),
                     paid_limits=2, paid_control=2, assigned_day='2026-10-10'):
    """Синтетика: ab_cohort + активность + orders (боевые/тестовые)."""
    from models import db
    from sqlalchemy import text
    from models import User
    db.session.execute(text('DELETE FROM ab_cohort'))
    db.session.execute(text('DELETE FROM orders'))
    db.session.execute(text('DELETE FROM daily_task_items'))
    db.session.execute(text('DELETE FROM daily_task_sets'))
    db.session.commit()
    a_ts = f'{assigned_day} 09:00:00'
    for i in range(n_limits):
        u = User(email=f'sl{i}@x.invalid', is_guest=False)
        db.session.add(u)
        db.session.flush()
        db.session.execute(text(
            "INSERT INTO ab_cohort (experiment_id, user_id, cohort, eligible_at, assigned_at, "
            "first_limit_shown_at, algo_version) VALUES ('limits_v1', :u, 'limits', :a, :a, :a, 't')"),
            {'u': u.id, 'a': a_ts})
        if i < int(n_limits * active_ratio[0]):
            _act(lapp, u.id, assigned_day)
            _act(lapp, u.id, (datetime.strptime(assigned_day, '%Y-%m-%d')
                              + timedelta(days=1)).strftime('%Y-%m-%d'))
    for i in range(n_control):
        u = User(email=f'sc{i}@x.invalid', is_guest=False)
        db.session.add(u)
        db.session.flush()
        db.session.execute(text(
            "INSERT INTO ab_cohort (experiment_id, user_id, cohort, eligible_at, assigned_at, "
            "first_limit_shown_at, algo_version) VALUES ('limits_v1', :u, 'control', :a, :a, NULL, 't')"),
            {'u': u.id, 'a': a_ts})
        if i < int(n_control * active_ratio[1]):
            _act(lapp, u.id, assigned_day)
            _act(lapp, u.id, (datetime.strptime(assigned_day, '%Y-%m-%d')
                              + timedelta(days=1)).strftime('%Y-%m-%d'))
    for k in range(paid_limits):
        db.session.execute(text(
            "INSERT INTO orders (id, payer_user_id, beneficiary_user_id, plan_code, "
            "amount, currency, price_version, status, is_test, paid_at, idempotence_key, "
            "created_at, updated_at) VALUES (:id, 1, 1, 'student_month', 49000, 'RUB', 't', "
            "'paid', :it, :p, :id, :p, :p)"),
            {'id': f'ord-l{k}', 'p': '2026-10-15 10:00:00', 'it': False})
    db.session.commit()


# ─────────────────────────── доступ ───────────────────────────
def test_anonymous_gets_404(lapp):
    """Требование промпта: «только для admin (иначе 404)» — без редиректа."""
    c = lapp.test_client()
    assert c.get('/admin/launch').status_code == 404
    assert c.get('/admin/launch.csv').status_code == 404


def test_non_admin_gets_404(lapp):
    # первый юзер получает id=1 (это админ) — не-админ это id>1
    _mk_admin(lapp)
    u = _mk_user(lapp, 'guest@x.invalid')
    c = _client(lapp, u)
    assert c.get('/admin/launch').status_code == 404
    assert c.get('/admin/launch.csv').status_code == 404


def test_flag_off_gets_404_even_for_admin(lapp, monkeypatch):
    monkeypatch.setenv('ADMIN_LAUNCH_ENABLED', '0')
    admin = _mk_admin(lapp)
    c = _client(lapp, admin)
    assert c.get('/admin/launch').status_code == 404


def test_admin_gets_200(lapp):
    _seed_experiment(lapp, n_limits=10, n_control=10)
    admin = _mk_admin(lapp)
    c = _client(lapp, admin)
    r = c.get('/admin/launch')
    assert r.status_code == 200
    assert 'Дашборд запуска' in r.get_data(as_text=True)


# ─────────────────────── содержимое блоков ───────────────────────
def test_missing_event_shows_no_source_not_zero(lapp):
    """Нет событий воронки родителя → «нет источника данных», не 0."""
    _seed_experiment(lapp, n_limits=10, n_control=10)
    admin = _mk_admin(lapp)
    c = _client(lapp, admin)
    txt = c.get('/admin/launch').get_data(as_text=True)
    assert 'нет источника данных' in txt
    # в CSV то же самое
    csv_txt = c.get('/admin/launch.csv').get_data(as_text=True)
    assert 'нет источника данных' in csv_txt


def test_free_grant_not_revenue(lapp):
    """Грант основателя и trial не считаются продажами: их нет в выручке."""
    _seed_experiment(lapp, n_limits=5, n_control=5)
    from models import db
    from sqlalchemy import text
    # грант основателя: 1 юзер, заказов нет
    db.session.execute(text(
        "INSERT INTO founder_grants (user_id, campaign_id, amount, starts_at, expires_at, "
        "granted_at) VALUES (1, 'founders_2026_v1', 0, '2026-11-01 00:00:00', "
        "'2027-02-01 00:00:00', '2026-10-05 10:00:00')"))
    db.session.commit()
    data = lm.collect(NOW)
    assert data['money']['founder_grants'] == 1
    # выручка только по orders paid is_test=0: 490 руб. с каждого из 2 заказов
    assert data['money']['monthly_equivalent'] == 980.0


def test_test_orders_excluded_from_revenue(lapp):
    """Тестовые платежи исключаются из выручки (явный is_test=1)."""
    _seed_experiment(lapp, n_limits=5, n_control=5)
    from models import db
    from sqlalchemy import text
    db.session.execute(text(
        "INSERT INTO orders (id, payer_user_id, beneficiary_user_id, plan_code, "
        "amount, currency, price_version, status, is_test, paid_at, idempotence_key, "
        "created_at, updated_at) VALUES ('ord-test', 1, 1, 'student_month', 49000, 'RUB', "
        "'t', 'paid', TRUE, '2026-10-15 10:00:00', 'ord-test', '2026-10-15 10:00:00', "
        "'2026-10-15 10:00:00')"))
    db.session.commit()
    data = lm.collect(NOW)
    # только 2 боевых заказа по 490 руб.
    assert data['money']['monthly_equivalent'] == 980.0


def test_unknown_is_test_excluded_from_confirmed_revenue(lapp):
    """is_test IS NULL (неизвестно) не считается подтверждённым боевым платежом."""
    _seed_experiment(lapp, n_limits=5, n_control=5, paid_limits=0)
    from models import db
    from sqlalchemy import text
    db.session.execute(text(
        "INSERT INTO orders (id, payer_user_id, beneficiary_user_id, plan_code, "
        "amount, currency, price_version, status, is_test, paid_at, idempotence_key, "
        "created_at, updated_at) VALUES ('ord-null', 1, 1, 'student_month', 49000, 'RUB', "
        "'t', 'paid', NULL, '2026-10-15 10:00:00', 'ord-null', '2026-10-15 10:00:00', "
        "'2026-10-15 10:00:00')"))
    db.session.commit()
    data = lm.collect(NOW)
    assert data['money']['monthly_equivalent'] in (0.0, None)
    assert data['money']['by_plan'] == []


def test_repeat_webhook_no_double_count(lapp):
    """Повторный webhook (confirm_payment дважды) не удваивает сумму."""
    _seed_experiment(lapp, n_limits=5, n_control=5, paid_limits=0)
    from models import db
    from models_billing import Order
    from services.billing.service import confirm_payment
    order = Order(payer_user_id=1, beneficiary_user_id=1, plan_code='student_month',
                 amount=49000, currency='RUB', price_version='t', status='created')
    db.session.add(order)
    db.session.commit()
    payment = {'id': f'pay-{order.id}', 'status': 'succeeded', 'paid': True,
               'amount': {'value': '490.00', 'currency': 'RUB'},
               'metadata': {'order_id': order.id}, 'test': False}
    r1 = confirm_payment(order.id, payment)
    r2 = confirm_payment(order.id, payment)   # повторный webhook
    assert r1 == 'paid'
    assert r2 == 'already_paid'              # идемпотентность
    # момент отчёта — реальное «сейчас»: paid_at заказа ставится utcnow
    data = lm.collect()
    # один заказ 490 руб. — сумма не удвоилась
    assert data['money']['monthly_equivalent'] == 490.0


def test_d7_incomplete_window_not_shown(lapp):
    """Назначение 3 дня назад → окно D7 неполное → d7_retained None (не 0)."""
    _seed_experiment(lapp, n_limits=10, n_control=10, assigned_day='2026-10-17')
    data = lm.collect(NOW)
    for g in data['experiment']['groups'].values():
        assert g['d7_retained'] is None
        assert g['d7_eligible'] == 0


def test_d7_full_window_shown(lapp):
    """Назначение 10-го + активность на 7-й день (17-е) → D7 показывается."""
    _seed_experiment(lapp, n_limits=10, n_control=10, assigned_day='2026-10-10')
    from models import db
    from sqlalchemy import text
    # активность на 7-й день у одного юзера группы limits
    row = db.session.execute(text(
        "SELECT user_id FROM ab_cohort WHERE experiment_id='limits_v1' "
        "AND cohort='limits' LIMIT 1")).fetchone()
    _act(lapp, row[0], '2026-10-17')
    data = lm.collect(NOW)
    g = data['experiment']['groups']['limits']
    assert g['d7_retained'] == 1
    assert g['d7_eligible'] == 10


def test_small_sample_insufficient_data(lapp):
    """Меньше LAUNCH_MIN_ELIGIBLE → «Недостаточно данных»."""
    _seed_experiment(lapp, n_limits=10, n_control=10)
    data = lm.collect(NOW)
    assert data['rule']['decision'] == 'Недостаточно данных'


def test_full_sample_rollout_decision(lapp):
    """200+200 назначенных, 10 полных суток с показа, доли равные, серии
    равные (нет источников серий → «Недостаточно данных», поэтому
    досеиваем события streak_day/streak_broken) → rollout."""
    from models import db
    from sqlalchemy import text
    _seed_experiment(lapp, n_limits=200, n_control=200, active_ratio=(0.5, 0.5))
    # у половины каждой группы есть серия, из них у 5% прервана
    rows = db.session.execute(text(
        "SELECT user_id, cohort FROM ab_cohort "
        "WHERE experiment_id='limits_v1'")).fetchall()
    for i, (uid, cohort) in enumerate(rows):
        if i % 2 == 0:
            _streak(lapp, uid, '2026-10-12', streak=3, broken=(i % 40 == 0))
    data = lm.collect(NOW)
    assert data['rule']['decision'] == 'Рассмотреть PAYWALL_MODE=rollout'


def test_rollout_decision_blocked_when_no_streak_events(lapp):
    """Серий нет (события не пишутся) → правило 11.11 не подставляет
    нули и отвечает «Недостаточно данных» — rollout не предлагается."""
    _seed_experiment(lapp, n_limits=200, n_control=200, active_ratio=(0.5, 0.5))
    data = lm.collect(NOW)
    assert data['rule']['decision'] == 'Недостаточно данных'
    ins = data['rule']['inputs']
    assert ins['broken_diff_pp'] is None     # NO_DATA; в CSV/HTML — «нет источника данных»


def test_rollout_decision_blocked_when_control_has_no_observations(lapp):
    """События серий есть ТОЛЬКО в limits (контроль: 0 наблюдений) →
    пустой знаменатель не подставляется контрольной долей 0:
    правило отвечает «Недостаточно данных», rollout не предлагается."""
    from models import db
    from sqlalchemy import text
    _seed_experiment(lapp, n_limits=200, n_control=200, active_ratio=(0.5, 0.5))
    # события только у пользователей группы limits
    rows = db.session.execute(text(
        "SELECT user_id FROM ab_cohort WHERE experiment_id='limits_v1' "
        "AND cohort='limits' LIMIT 100")).fetchall()
    for uid, in rows:
        _streak(lapp, uid, '2026-10-12', streak=3, broken=False)
    data = lm.collect(NOW)
    g_c = data['experiment']['groups']['control']
    assert g_c['streak_users'] == 0            # сырой счётчик сохранён
    # отображение: «нет наблюдений», не доля 0/0
    assert data['rule']['decision'] == 'Недостаточно данных'
    assert data['rule']['inputs']['broken_diff_pp'] is None
    rows_csv = lm.to_csv_rows(data)
    row = [r for r in rows_csv if r[0] == 'эксперимент/control' and r[1] == 'прерванные серии']
    assert row and row[0][2] == 'нет наблюдений (0/0)'


def test_funnel_exact_values(lapp):
    """Точная воронка по людям: события/заказы только в окне
    [назначение; NOW) и только у юзеров группы."""
    from models import db
    from sqlalchemy import text
    from models import User
    db.session.execute(text('DELETE FROM ab_cohort'))
    db.session.execute(text('DELETE FROM orders'))
    db.session.execute(text('DELETE FROM funnel_events'))
    db.session.commit()
    # 10 юзеров в limits; окно: назначены 2026-10-10, отчёт 2026-10-20
    uids = []
    for i in range(10):
        u = User(email=f'fl{i}@x.invalid', is_guest=False)
        db.session.add(u)
        db.session.flush()
        uids.append(u.id)
        db.session.execute(text(
            "INSERT INTO ab_cohort (experiment_id, user_id, cohort, eligible_at, "
            "assigned_at, first_limit_shown_at, algo_version) VALUES "
            "('limits_v1', :u, 'limits', :a, :a, :a, 't')"),
            {'u': u.id, 'a': '2026-10-10 09:00:00'})
    db.session.commit()
    # показ: 6 юзеров (5 в окне + 1 ДО назначения — не считается)
    for uid in uids[:5]:
        _ev(lapp, uid, 'limit_shown', '2026-10-11')
    _ev(lapp, uids[5], 'limit_shown', '2026-10-09')   # до окна
    _ev(lapp, uids[6], 'limit_shown', '2026-10-21')   # после as_of
    # визит /subscribe: 4 из показавших
    for uid in uids[:4]:
        _ev(lapp, uid, 'subscribe_view', '2026-10-12')
    # заказы: 3 юзера, из них 1 заказ ДО назначения (не считается),
    # 1 тестовый оплаченный (не считается в боевые)
    for k, uid in enumerate(uids[:3]):
        paid_at = '2026-10-15 10:00:00' if k == 0 else None
        db.session.execute(text(
            "INSERT INTO orders (id, payer_user_id, beneficiary_user_id, plan_code, "
            "amount, currency, price_version, status, is_test, paid_at, "
            "idempotence_key, created_at, updated_at) VALUES "
            "(:id, :u, :u, 'student_month', 49000, 'RUB', 't', 'paid', :it, :p, "
            ":id, :c, :c)"),
            {'id': f'fx-{k}', 'u': uid, 'it': False,
             'p': paid_at, 'c': '2026-10-14 10:00:00'})
    # заказ до окна (created_at до назначения) и тестовая оплата
    db.session.execute(text(
        "INSERT INTO orders (id, payer_user_id, beneficiary_user_id, plan_code, "
        "amount, currency, price_version, status, is_test, paid_at, idempotence_key, "
        "created_at, updated_at) VALUES ('fx-old', :u, :u, 'student_month', 49000, "
        "'RUB', 't', 'paid', :it, '2026-10-05 10:00:00', 'fx-old', "
        "'2026-10-05 10:00:00', '2026-10-05 10:00:00')"),
        {'u': uids[7], 'it': False})
    db.session.execute(text(
        "INSERT INTO orders (id, payer_user_id, beneficiary_user_id, plan_code, "
        "amount, currency, price_version, status, is_test, paid_at, idempotence_key, "
        "created_at, updated_at) VALUES ('fx-test', :u, :u, 'student_month', 49000, "
        "'RUB', 't', 'paid', :it, '2026-10-16 10:00:00', 'fx-test', "
        "'2026-10-16 10:00:00', '2026-10-16 10:00:00')"),
        {'u': uids[8], 'it': True})
    db.session.execute(text(
        "INSERT INTO orders (id, payer_user_id, beneficiary_user_id, plan_code, "
        "amount, currency, price_version, status, is_test, paid_at, idempotence_key, "
        "created_at, updated_at) VALUES ('fx-null', :u, :u, 'student_month', 49000, "
        "'RUB', 't', 'paid', :it, '2026-10-17 10:00:00', 'fx-null', "
        "'2026-10-17 10:00:00', '2026-10-17 10:00:00')"),
        {'u': uids[9], 'it': None})
    db.session.commit()
    data = lm.collect(NOW)
    g = data['experiment']['groups']['limits']
    assert g['shown'] == 5            # 5 в окне, до/после — нет
    assert g['subscribe_view'] == 4
    assert g['order_created'] == 3     # fx-0..2; fx-old вне окна, fx-test тестовый
    assert g['paid'] == 1              # только fx-0: боевой + paid_at в окне
    # fx-null: is_test=NULL (неизвестно) — исключён из воронки (fail-closed)


def test_few_days_insufficient_data(lapp):
    """Группы достаточны, но с показа < 7 полных суток → недостаточно данных."""
    _seed_experiment(lapp, n_limits=200, n_control=200, assigned_day='2026-10-16')
    data = lm.collect(NOW)
    assert data['rule']['decision'] == 'Недостаточно данных'


# ─────────────────────────── CSV ───────────────────────────
def test_csv_same_data_as_html(lapp, monkeypatch):
    """CSV и HTML построены из ОДНОГО collect() (as_of зафиксирован):
    каждая метрика CSV сверяется с конкретной ячейкой HTML по data-metric,
    включая «нет источника данных», ДИ и составные ячейки. HTML не
    показывает 0/0 или None там, где источник отсутствует."""
    import csv as _csv
    import re as _re
    _seed_experiment(lapp, n_limits=10, n_control=10)
    # события серий и воронки — чтобы покрыть и непустые метрики
    from models import db
    from sqlalchemy import text
    rows = db.session.execute(text(
        "SELECT user_id, cohort FROM ab_cohort WHERE experiment_id='limits_v1' "
        "ORDER BY user_id LIMIT 4")).fetchall()
    for i, (uid, cohort) in enumerate(rows):
        if i % 2 == 0:
            _streak(lapp, uid, '2026-10-12', streak=3, broken=(i == 0))
        _ev(lapp, uid, 'limit_shown', '2026-10-11')
        if i < 2:
            _ev(lapp, uid, 'subscribe_view', '2026-10-12')
    admin = _mk_admin(lapp)
    c = _client(lapp, admin)
    # фиксируем ОДИН набор данных для обоих ответов
    real_collect = lm.collect
    captured = {}

    def fixed_collect():
        if 'd' not in captured:
            captured['d'] = real_collect()
        return captured['d']

    monkeypatch.setattr(lm, 'collect', fixed_collect)
    html = c.get('/admin/launch').get_data(as_text=True)
    csv_resp = c.get('/admin/launch.csv')
    assert csv_resp.status_code == 200
    csv_txt = csv_resp.get_data(as_text=True)

    # ячейки HTML по data-metric="section|metric" (стековый разбор:
    # поддерживает вложенные small/span внутри td)
    from html.parser import HTMLParser

    class CellParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack = []            # (tag, key|None)
            self.cells = {}            # key -> text

        def handle_starttag(self, tag, attrs):
            key = dict(attrs).get('data-metric')
            self.stack.append([tag, key, []])
            if tag not in ('br', 'img', 'hr'):
                pass

        def handle_endtag(self, tag):
            # найти ближайший незакрытый элемент с этим тегом
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    # закрыть все от i до конца (незакрытые внутренние)
                    for j in range(len(self.stack) - 1, i - 1, -1):
                        el = self.stack.pop(j)
                        text = ''.join(el[2])
                        text = _re.sub(r'\s+', ' ', text).strip()
                        if el[1]:
                            self.cells.setdefault(el[1], text)
                    return

        def handle_data(self, data):
            for el in self.stack:
                el[2].append(data)

    cp = CellParser()
    cp.feed(html)
    cells_raw = cp.cells
    assert cells_raw, 'в шаблоне должны быть data-metric ячейки'

    rows_csv = list(_csv.reader(csv_txt.splitlines(), delimiter=';'))
    assert rows_csv[0] == ['section', 'metric', 'value']
    checked = 0
    for section, metric, value in rows_csv[1:]:
        assert len([r for r in rows_csv[1:] if r[0] == section and r[1] == metric]) == 1
        key = f'{section}|{metric}'
        assert key in cells_raw, f'в HTML нет ячейки data-metric="{key}"'
        cell = cells_raw[key]
        v = value[1:] if value.startswith("'") else value   # formula-escape
        if v == 'нет источника данных':
            assert 'нет источника данных' in cell, (key, cell)
        else:
            # значение встречается в ячейке как отдельное число/токен
            assert _re.search(r'(?<![\d.])' + _re.escape(v) + r'(?![\d.])', cell), \
                (key, v, cell)
        checked += 1
    assert checked >= 40, f'проверено слишком мало метрик: {checked}'
    # ND-метрики в датасете присутствуют (серии/воронка родителя без событий)
    nd = [r for r in rows_csv[1:] if r[2] == 'нет источника данных']
    assert nd, 'в фиксированном датасете должны быть метрики без источника'
    # HTML не показывает None вместо ND; «0/0» бывает честным значением
    # (0 пользователей с сериями при существующем источнике) — маскировку ND
    # исключает по-ячейковая сверка выше
    assert '>None<' not in html and 'None ' not in html


def test_csv_formula_injection_sanitized(lapp):
    """Ячейка, начинающаяся с =/+/-/@, получает префикс-апостроф."""
    assert lm.csv_escape('=SUM(A1)') == "'=SUM(A1)"
    assert lm.csv_escape('+cmd') == "'+cmd"
    assert lm.csv_escape('-1') == "'-1"
    assert lm.csv_escape('@x') == "'@x"
    assert lm.csv_escape('обычное') == 'обычное'
    # источник события с utm-параметром-атакой не ломает CSV:
    # ни одна ячейка не НАЧИНАЕТСЯ с опасного символа
    rows = lm.to_csv_rows({'sources': {'by_utm_source': [('=SUM(A1)', 3)],
                                       'by_utm_campaign': [], 'by_acq_source': []},
                          'readiness': {}, 'money': {}, 'rule': {}})
    for row in rows:
        for cell in row[1:]:          # header-строку не проверяем
            assert str(cell)[:1] not in ('=', '+', '@'), cell
            assert not (str(cell)[:1] == '-' and not str(cell).startswith("'")), cell


def test_csv_requires_admin(lapp):
    _mk_admin(lapp)
    u = _mk_user(lapp, 'csvguest@x.invalid')
    c = _client(lapp, u)
    assert c.get('/admin/launch.csv').status_code == 404


def test_no_secrets_in_page(lapp):
    """В странице нет email (включая админа), токенов ссылок, payload платежей."""
    _mk_admin(lapp)
    _seed_experiment(lapp, n_limits=5, n_control=5)
    admin = _mk_admin(lapp)
    c = _client(lapp, admin)
    txt = c.get('/admin/launch').get_data(as_text=True)
    # email синтетических пользователей и админа не выводится
    assert 'sl0@x.invalid' not in txt
    assert 'sc0@x.invalid' not in txt
    assert 'admin@x.invalid' not in txt
    assert 'confirmation_url' not in txt
    assert 'yookassa_payment_id' not in txt




