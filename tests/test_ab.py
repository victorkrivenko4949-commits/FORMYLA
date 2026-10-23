# -*- coding: utf-8 -*-
"""AB_V1 — тесты A/B-групп (промпт 18).

Запуск: pytest tests/test_ab.py -q
"""
from datetime import date, datetime, timedelta, timezone

import pytest

import services.ab as ab
from services.ab import apply_limits, assign_cohort, cohort_for

LAUNCH = datetime(2026, 10, 31, 21, 0, tzinfo=timezone.utc)   # 01.11.2026 00:00 МСК
AFTER = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
BEFORE = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def abapp(app, monkeypatch):
    monkeypatch.setenv('PAYWALL_MODE', 'experiment')
    monkeypatch.setenv('PAYWALL_START_AT', '2026-10-31T21:00:00Z')
    monkeypatch.setenv('PAYWALL_EXPERIMENT_ID', 'limits_v1')
    monkeypatch.setenv('PAYWALL_AB', '50')
    monkeypatch.delenv('AB_EXCLUDE_USER_IDS', raising=False)
    monkeypatch.delenv('FOUNDER_EXCLUDE_USER_IDS', raising=False)
    from models import db
    from sqlalchemy import text
    db.create_all()
    # usage_daily / funnel_events нужны отчёту и событиям (диалект-совместимо)
    pg = db.engine.dialect.name == 'postgresql'
    serial = 'SERIAL PRIMARY KEY' if pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    ddls = [
        f"""CREATE TABLE IF NOT EXISTS usage_daily (
            id {serial}, user_id INTEGER NOT NULL,
            date TEXT NOT NULL, tasks_completed INTEGER DEFAULT 0,
            ai_explanations_used INTEGER DEFAULT 0, tokens_consumed INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS funnel_events (
            id {s}, user_id INTEGER, anon_id VARCHAR(36),
            event VARCHAR(40) NOT NULL, props TEXT, source VARCHAR(40), ref VARCHAR(80),
            path VARCHAR(200), referrer VARCHAR(300), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""".format(s=serial),
        """CREATE TABLE IF NOT EXISTS subscriptions (
            id {s}, user_id INTEGER NOT NULL, plan TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active', started_at TIMESTAMP, expires_at TIMESTAMP,
            payment_method TEXT, payment_id TEXT, amount_rub INTEGER, is_trial INTEGER DEFAULT 0,
            is_beta_access INTEGER DEFAULT 1, created_at TIMESTAMP)""".format(s=serial),
    ]
    for ddl in ddls:
        db.session.execute(text(ddl))
    db.session.commit()
    return app


def _mk_user(abapp, email, **kw):
    from models import db, User
    u = User(email=email, is_guest=False, **kw)
    db.session.add(u)
    db.session.commit()
    return u


def _n_rows():
    from models_ab import AbCohort
    return AbCohort.query.count()


# ─────────────────────────── распределение ───────────────────────────

def test_10k_ids_45_55_percent():
    """10 000 id → 45–55% в limits (при PAYWALL_AB=50)."""
    n_limits = sum(1 for uid in range(1, 10001)
                   if cohort_for('limits_v1', uid, percent=50) == 'limits')
    assert 4500 <= n_limits <= 5500


def test_percent_change_keeps_assigned_group(abapp, monkeypatch):
    """PAYWALL_AB 50 → 100 → 0 не меняет уже назначенную группу."""
    u = _mk_user(abapp, 'ab1@x.invalid')
    first = assign_cohort(u, now=AFTER)
    assert first in ('limits', 'control')
    monkeypatch.setenv('PAYWALL_AB', '100')
    assert ab.get_cohort(u.id) == first
    monkeypatch.setenv('PAYWALL_AB', '0')
    # повторное обращение не переназначает: строка уже есть
    assert assign_cohort(u, now=AFTER) == first
    # и новый пользователь при 0% не попадает в limits — но это НЕ влияет на старых
    u2 = _mk_user(abapp, 'ab2@x.invalid')
    assert cohort_for('limits_v1', u2.id, percent=0) == 'control'


# ─────────────────────────── режимы ───────────────────────────

def test_off_mode_no_assignment_and_no_limits(abapp, monkeypatch):
    monkeypatch.setenv('PAYWALL_MODE', 'off')
    u = _mk_user(abapp, 'off@x.invalid')
    assert apply_limits(u, now=AFTER) is False
    assert _n_rows() == 0


def test_rollout_limits_all_free_and_keeps_rows(abapp, monkeypatch):
    monkeypatch.setattr(ab, 'cohort_for', lambda e, uid, percent=None: 'limits')
    u = _mk_user(abapp, 'roll@x.invalid')
    assert apply_limits(u, now=AFTER) is True       # experiment: назначение + limits
    n_before = _n_rows()
    monkeypatch.setenv('PAYWALL_MODE', 'rollout')
    u2 = _mk_user(abapp, 'roll2@x.invalid')
    assert apply_limits(u2, now=AFTER) is True      # rollout: лимит всем free
    # строки ab_cohort не изменились: u2 не назначался в rollout
    assert _n_rows() == n_before


def test_before_start_no_limits(abapp):
    u = _mk_user(abapp, 'early@x.invalid')
    assert apply_limits(u, now=BEFORE) is False
    assert _n_rows() == 0


def test_mode_off_during_limits_and_rollout_during_control(abapp, monkeypatch):
    """off при группе limits и rollout при control — строки ab_cohort не изменились."""
    u = _mk_user(abapp, 'mix1@x.invalid')
    c1 = assign_cohort(u, now=AFTER)
    u2 = _mk_user(abapp, 'mix2@x.invalid')
    c2 = assign_cohort(u2, now=AFTER)
    rows_before = {(r.user_id, r.cohort) for r in _all_rows()}
    monkeypatch.setenv('PAYWALL_MODE', 'off')
    assert apply_limits(u, now=AFTER) is False
    monkeypatch.setenv('PAYWALL_MODE', 'rollout')
    assert apply_limits(u, now=AFTER) is True
    assert apply_limits(u2, now=AFTER) is True
    rows_after = {(r.user_id, r.cohort) for r in _all_rows()}
    assert rows_before == rows_after


def _all_rows():
    from models_ab import AbCohort
    return AbCohort.query.all()


# ─────────────────────────── кто не назначается ───────────────────────────

def test_founder_and_trial_and_paid_not_assigned(abapp):
    from models import db
    from models_founders import FounderGrant
    # триал
    u_trial = _mk_user(abapp, 't@x.invalid', trial_until=AFTER + timedelta(days=10))
    assert apply_limits(u_trial, now=AFTER) is False
    # Основатель
    u_f = _mk_user(abapp, 'f@x.invalid')
    db.session.add(FounderGrant(user_id=u_f.id, campaign_id='founders_2026_v1', amount=0,
                                is_free_grant=True, starts_at=datetime(2026, 10, 31, 21),
                                expires_at=datetime(2027, 1, 31, 21), granted_by='test'))
    db.session.commit()
    assert apply_limits(u_f, now=AFTER) is False
    # оплаченный доступ
    u_p = _mk_user(abapp, 'p@x.invalid')
    from services.subscription import get_subscription_service
    get_subscription_service().activate_premium(
        u_p.id, payment_id='pay_ab', is_beta=False, amount_rub=490,
        starts_at=datetime(2026, 11, 1), expires_at=datetime(2026, 12, 1))
    db.session.commit()
    assert apply_limits(u_p, now=AFTER) is False
    assert _n_rows() == 0


def test_purchase_after_assignment_removes_limit_but_keeps_group(abapp, monkeypatch):
    monkeypatch.setattr(ab, 'cohort_for', lambda e, uid, percent=None: 'limits')
    from models import db
    from models_ab import AbCohort
    u = _mk_user(abapp, 'buy@x.invalid')
    assert apply_limits(u, now=AFTER) is True
    row = AbCohort.query.filter_by(user_id=u.id).one()
    cohort = row.cohort
    # покупка после назначения
    from services.subscription import get_subscription_service
    get_subscription_service().activate_premium(
        u.id, payment_id='pay_ab2', is_beta=False, amount_rub=490,
        starts_at=datetime(2026, 11, 6), expires_at=datetime(2026, 12, 6))
    db.session.commit()
    assert apply_limits(u, now=datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)) is False  # лимит снят
    assert AbCohort.query.filter_by(user_id=u.id).one().cohort == cohort  # группа та же


def test_manual_exclusion(abapp, monkeypatch):
    u = _mk_user(abapp, 'ex@x.invalid')
    monkeypatch.setenv('AB_EXCLUDE_USER_IDS', str(u.id))
    assert apply_limits(u, now=AFTER) is False
    assert _n_rows() == 0


# ─────────────────────────── идемпотентность ───────────────────────────

def test_repeat_and_double_assign_one_row(abapp):
    """Повторный вызов и «конкурентный» INSERT (ON CONFLICT DO NOTHING) → одна строка."""
    from models_ab import AbCohort
    u = _mk_user(abapp, 'idem@x.invalid')
    c = assign_cohort(u, now=AFTER)
    assert assign_cohort(u, now=AFTER) == c
    # прямая конкурентная вставка той же строки
    from models import db
    from sqlalchemy import text
    sql = ("INSERT INTO ab_cohort (experiment_id, user_id, cohort, assigned_at, "
           "eligible_at, algo_version) VALUES ('limits_v1', :u, :c, :a, :a, :v) ON CONFLICT DO NOTHING")
    db.session.execute(text(sql), {'u': u.id, 'c': c, 'a': AFTER.replace(tzinfo=None),
                                   'v': ab.ALGO_VERSION})
    db.session.commit()
    assert AbCohort.query.filter_by(user_id=u.id).count() == 1


def test_new_experiment_new_assignment(abapp, monkeypatch):
    u = _mk_user(abapp, 'newexp@x.invalid')
    c1 = assign_cohort(u, now=AFTER)
    assert _n_rows() == 1
    monkeypatch.setenv('PAYWALL_EXPERIMENT_ID', 'limits_v2')
    c2 = assign_cohort(u, now=AFTER)
    assert _n_rows() == 2                            # новый experiment_id → новое назначение
    assert c2 in ('limits', 'control')


def test_assignment_error_fail_open(abapp, monkeypatch):
    """Ошибка назначения → лимит не применяется (fail-open), сайт не падает."""
    u = _mk_user(abapp, 'err@x.invalid')
    monkeypatch.setattr(ab, 'get_cohort', lambda uid, exp=None: (_ for _ in ()).throw(RuntimeError('db gone')))
    assert apply_limits(u, now=AFTER) is False


def test_events_written(abapp):
    u = _mk_user(abapp, 'ev@x.invalid')
    assign_cohort(u, now=AFTER)
    from sqlalchemy import text
    from models import db
    events = {r[0] for r in db.session.execute(
        text("SELECT DISTINCT event FROM funnel_events WHERE user_id=:u"), {'u': u.id}).fetchall()}
    assert 'ab_assigned' in events and 'ab_first_eligible_request' in events


# ─────────────────────────── отчёт ───────────────────────────

def test_report_metrics_and_incomplete_d7(abapp):
    """Отчёт считает метрики по исходному назначению; неполный D7 не выводится."""
    from models import db
    from models_billing import Order
    from routes.ab import build_report

    # user_l: limits, активен 7 дней, оплата
    user_l = _mk_user(abapp, 'rep_l@x.invalid')
    user_c = _mk_user(abapp, 'rep_c@x.invalid')
    monkeypatch_pct = None
    # принудительно назначаем группы
    from models_ab import AbCohort
    assigned_at = datetime(2026, 11, 5, 18, 0)      # 21:00 МСК 05.11
    db.session.add(AbCohort(experiment_id='limits_v1', user_id=user_l.id, cohort='limits',
                           assigned_at=assigned_at, eligible_at=assigned_at,
                           algo_version=ab.ALGO_VERSION))
    db.session.add(AbCohort(experiment_id='limits_v1', user_id=user_c.id, cohort='control',
                            assigned_at=assigned_at, eligible_at=assigned_at,
                            algo_version=ab.ALGO_VERSION))
    # активность: limits отвечает на задачи 6 дней из окна, control — 1 день.
    # Активность = ответ на задачу дня (daily_task_items.user_answer), не usage_daily.
    def _act(uid, day, n):
        from daily_tasks.models import DailyTaskSet, DailyTaskItem
        s = DailyTaskSet(user_id=uid, target_date=datetime.strptime(day, '%Y-%m-%d').date(),
                        status='ready')
        db.session.add(s)
        db.session.flush()
        for i in range(n):
            db.session.add(DailyTaskItem(daily_set_id=s.id, position=i + 1,
                                        task_text='t', user_answer='1',
                                        answered_at=datetime(2026, 11, 6, 12)))
    for d in range(6):
        _act(user_l.id, f'2026-11-{6 + d:02d}', 3)
    _act(user_c.id, '2026-11-06', 2)
    # оплата у limits после назначения
    db.session.add(Order(payer_user_id=user_l.id, beneficiary_user_id=user_l.id,
                         plan_code='student_month', amount=49000, price_version='t',
                         status='paid', paid_at=datetime(2026, 11, 8), is_test=False))
    db.session.commit()

    # окно наблюдения: назначение 05.11 + 7 дней = 12.11 <= as_of 15.11 → полный D7
    rep = build_report('limits_v1', datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc))
    g_l = rep['groups']['limits']
    assert g_l['assigned'] == 1
    assert g_l['active_7d'] == 1 and g_l['tasks_total_7d'] == 18
    assert g_l['paid_after_assignment'] == 1
    assert g_l['d7_retained'] == 0    # 12.11 не решал
    g_c = rep['groups']['control']
    assert g_c['active_7d'] == 1 and g_c['tasks_total_7d'] == 2
    assert g_c['paid_after_assignment'] == 0

    # неполное окно: as_of 10.11 → D7 не выводится
    rep2 = build_report('limits_v1', datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc))
    assert rep2['groups']['limits']['d7_retained'] is None


def test_test_payments_excluded_from_conversion(abapp):
    from models import db
    from models_billing import Order
    from models_ab import AbCohort
    from routes.ab import build_report
    u = _mk_user(abapp, 'tp@x.invalid')
    db.session.add(AbCohort(experiment_id='limits_v1', user_id=u.id, cohort='limits',
                            assigned_at=datetime(2026, 11, 5, 18), eligible_at=datetime(2026, 11, 5, 18),
                            algo_version=ab.ALGO_VERSION))
    db.session.add(Order(payer_user_id=u.id, beneficiary_user_id=u.id, plan_code='student_month',
                         amount=49000, price_version='t', status='paid',
                         paid_at=datetime(2026, 11, 8), is_test=True))
    db.session.commit()
    rep = build_report('limits_v1', datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc))
    assert rep['groups']['limits']['paid_after_assignment'] == 0


# ── LAUNCH_V1 ревизия: серии по событиям, активность по answered_at ──
def _ev(app_, user_id, event, created, props=None):
    import json as _json
    from models import db
    db.session.execute(db.text(
        "INSERT INTO funnel_events (user_id, event, props, created_at) "
        "VALUES (:u, :e, :p, :c)"),
        {'u': user_id, 'e': event, 'p': _json.dumps(props or {}), 'c': created})
    db.session.commit()


def test_broken_series_no_source_without_events(abapp):
    """Без событий streak_day/streak_broken — «нет источника данных» (None)."""
    from routes.ab import build_report
    rep = build_report('limits_v1', datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc))
    for g in rep['groups'].values():
        assert g['broken_streaks'] is None
        assert g['streak_users'] is None
        assert g['broken_share'] is None


def test_broken_series_from_events(abapp):
    """Серии считаются по событиям: streak>=2 = была серия, streak_broken = прервана."""
    from models import db
    from models_ab import AbCohort
    from routes.ab import build_report
    import services.ab as ab_mod
    u1 = _mk_user(abapp, 'sv1@x.invalid')
    u2 = _mk_user(abapp, 'sv2@x.invalid')
    db.session.add(AbCohort(experiment_id='limits_v1', user_id=u1.id, cohort='limits',
                            assigned_at=datetime(2026, 11, 5, 18),
                            eligible_at=datetime(2026, 11, 5, 18),
                            algo_version=ab_mod.ALGO_VERSION))
    db.session.add(AbCohort(experiment_id='limits_v1', user_id=u2.id, cohort='limits',
                            assigned_at=datetime(2026, 11, 5, 18),
                            eligible_at=datetime(2026, 11, 5, 18),
                            algo_version=ab_mod.ALGO_VERSION))
    db.session.commit()
    # u1: серия (streak 2, 3) и потом сброс — прервана
    _ev(abapp, u1.id, 'streak_day', '2026-11-07 12:00:00', {'streak': 2})
    _ev(abapp, u1.id, 'streak_day', '2026-11-08 12:00:00', {'streak': 3})
    _ev(abapp, u1.id, 'streak_broken', '2026-11-10 12:00:00')
    # u2: серия есть (streak 2), сброса нет
    _ev(abapp, u2.id, 'streak_day', '2026-11-07 12:00:00', {'streak': 2})
    rep = build_report('limits_v1', datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc))
    g = rep['groups']['limits']
    assert g['streak_users'] == 2
    assert g['broken_streaks'] == 1
    assert g['broken_share'] == 0.5


def test_broken_series_event_outside_window_ignored(abapp):
    """Событие до назначения или после момента отчёта не считается."""
    from models import db
    from models_ab import AbCohort
    from routes.ab import build_report
    import services.ab as ab_mod
    u = _mk_user(abapp, 'sv3@x.invalid')
    db.session.add(AbCohort(experiment_id='limits_v1', user_id=u.id, cohort='limits',
                            assigned_at=datetime(2026, 11, 5, 18),
                            eligible_at=datetime(2026, 11, 5, 18),
                            algo_version=ab_mod.ALGO_VERSION))
    db.session.commit()
    _ev(abapp, u.id, 'streak_broken', '2026-11-01 12:00:00')   # до назначения
    _ev(abapp, u.id, 'streak_day', '2026-11-20 12:00:00', {'streak': 2})  # после as_of
    rep = build_report('limits_v1', datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc))
    g = rep['groups']['limits']
    assert g['streak_users'] == 0
    assert g['broken_streaks'] == 0


def test_late_answer_counts_on_answer_date(abapp):
    """Долг закрыт позже — день активности = дата ответа (answered_at), не target_date."""
    from models import db
    from models_ab import AbCohort
    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    from routes.ab import build_report
    import services.ab as ab_mod
    u = _mk_user(abapp, 'late1@x.invalid')
    db.session.add(AbCohort(experiment_id='limits_v1', user_id=u.id, cohort='limits',
                            assigned_at=datetime(2026, 11, 5, 18),
                            eligible_at=datetime(2026, 11, 5, 18),
                            algo_version=ab_mod.ALGO_VERSION))
    # сет от 06.11, ответ дан 12.11 → активность на 12.11 (МСК), не на 06.11
    s = DailyTaskSet(user_id=u.id, target_date=date(2026, 11, 6), status='ready')
    db.session.add(s)
    db.session.flush()
    db.session.add(DailyTaskItem(daily_set_id=s.id, position=1, task_text='t',
                                 user_answer='1', answered_at=datetime(2026, 11, 12, 9)))
    db.session.commit()
    rep = build_report('limits_v1', datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc))
    g = rep['groups']['limits']
    assert g['active_7d'] == 1
    # окно [05.11; 12.11] (7 дней от назначения) — 12.11 внутри окна


def test_answer_after_asof_excluded(abapp):
    """Ответ после момента отчёта не попадает в метрики."""
    from models import db
    from models_ab import AbCohort
    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    from routes.ab import build_report
    import services.ab as ab_mod
    u = _mk_user(abapp, 'late2@x.invalid')
    db.session.add(AbCohort(experiment_id='limits_v1', user_id=u.id, cohort='limits',
                            assigned_at=datetime(2026, 11, 5, 18),
                            eligible_at=datetime(2026, 11, 5, 18),
                            algo_version=ab_mod.ALGO_VERSION))
    s = DailyTaskSet(user_id=u.id, target_date=date(2026, 11, 6), status='ready')
    db.session.add(s)
    db.session.flush()
    db.session.add(DailyTaskItem(daily_set_id=s.id, position=1, task_text='t',
                                 user_answer='1', answered_at=datetime(2026, 11, 16, 9)))
    db.session.commit()
    rep = build_report('limits_v1', datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc))
    g = rep['groups']['limits']
    assert g['active_7d'] == 0


# ──────────────────── предпросмотр для админов ────────────────────

def test_admin_preview_off_by_default(abapp, monkeypatch):
    """PAYWALL_PREVIEW_ADMINS не задан → предпросмотр выключен (дефолт)."""
    import services.ab as _ab
    monkeypatch.setenv('PAYWALL_MODE', 'off')
    import services.ab as ab
    monkeypatch.delenv('PAYWALL_PREVIEW_ADMINS', raising=False)
    admin = _mk_user(abapp, 'kr1venkovictor@yandex.ru', nickname='victor')
    assert ab.mode() == 'off'
    assert ab.apply_limits(admin) is False


def test_admin_preview_admin_only(abapp, monkeypatch):
    """PAYWALL_MODE=off + PAYWALL_PREVIEW_ADMINS=1 → лимиты видит ТОЛЬКО
    админ (доступ free); обычный пользователь не затронут."""
    import services.ab as _ab
    monkeypatch.setenv('PAYWALL_MODE', 'off')
    import services.ab as ab
    monkeypatch.setenv('PAYWALL_PREVIEW_ADMINS', '1')
    admin = _mk_user(abapp, 'pv-admin@x.invalid', nickname='lavrik')
    plain = _mk_user(abapp, 'pv-plain@x.invalid', nickname='plain')
    assert ab.apply_limits(admin) is True
    assert ab.apply_limits(plain) is False


def test_admin_preview_ignores_start_date(abapp, monkeypatch):
    """Предпросмотр работает ДО 03.11: старт-дата на него не влияет."""
    import services.ab as _ab
    monkeypatch.setenv('PAYWALL_MODE', 'off')
    import services.ab as ab
    from datetime import datetime, timezone
    monkeypatch.setenv('PAYWALL_PREVIEW_ADMINS', '1')
    monkeypatch.setenv('PAYWALL_START_AT', '2026-11-02T21:00:00Z')
    admin = _mk_user(abapp, 'pv-early@x.invalid', nickname='lavrik')
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)   # до старта
    assert ab.apply_limits(admin, now=now) is True


def test_admin_preview_paid_admin_not_limited(abapp, monkeypatch):
    """Админ с платным доступом предпросмотром не затрагивается."""
    import services.ab as _ab
    monkeypatch.setenv('PAYWALL_MODE', 'off')
    import services.ab as ab
    from models import db
    from models_founders import FounderGrant
    from datetime import datetime
    monkeypatch.setenv('PAYWALL_PREVIEW_ADMINS', '1')
    admin = _mk_user(abapp, 'pv-paid@x.invalid', nickname='lavrik')
    # грант АКТИВЕН сейчас (реальное время теста), доступ не free
    db.session.add(FounderGrant(
        user_id=admin.id, campaign_id='founders_2026_v1', amount=0,
        is_free_grant=True, starts_at=datetime(2026, 10, 1, 0),
        expires_at=datetime(2027, 1, 31, 21)))
    db.session.commit()
    assert ab.apply_limits(admin) is False


def test_admin_preview_overridden_by_mode(abapp, monkeypatch):
    """PAYWALL_MODE=rollout перекрывает предпросмотр: лимиты для всех free."""
    import services.ab as ab
    from datetime import datetime, timezone
    monkeypatch.setenv('PAYWALL_PREVIEW_ADMINS', '1')
    monkeypatch.setenv('PAYWALL_MODE', 'rollout')
    plain = _mk_user(abapp, 'pv-roll@x.invalid', nickname='plain')
    now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)   # после старта
    assert ab.apply_limits(plain, now=now) is True
