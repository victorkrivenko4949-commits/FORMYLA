# -*- coding: utf-8 -*-
"""FOUNDERS_V1 — тесты задачи «Основатели + resolve_access».

Запуск: pytest tests/test_founders.py -q
На PostgreSQL: BILLING_TEST_PG_URL=... pytest tests/test_founders.py -q
"""
import argparse
from datetime import datetime, timedelta, timezone

import pytest

from services.access import resolve_access, founder_cutoff, founder_grant_until

CUTOFF_NAIVE = datetime(2026, 11, 2, 21, 0, 0)       # 03.11.2026 00:00 МСК
UNTIL_NAIVE = datetime(2027, 1, 31, 21, 0, 0)        # 01.02.2027 00:00 МСК
NOW_LAUNCH = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def found_app(app):
    from models import db
    from sqlalchemy import text
    db.create_all()
    # subscriptions не в metadata (migrations/002) — создаём как в billing-тестах
    if db.engine.dialect.name == 'postgresql':
        db.session.execute(text("""CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL, plan TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active', started_at TIMESTAMP, expires_at TIMESTAMP,
            payment_method TEXT, payment_id TEXT, amount_rub INTEGER, is_trial INTEGER DEFAULT 0,
            is_beta_access INTEGER DEFAULT 1, created_at TIMESTAMP)"""))
    else:
        db.session.execute(text("""CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, plan TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active', started_at TIMESTAMP, expires_at TIMESTAMP,
            payment_method TEXT, payment_id TEXT, amount_rub INTEGER, is_trial INTEGER DEFAULT 0,
            is_beta_access INTEGER DEFAULT 1, created_at TIMESTAMP)"""))
    db.session.commit()
    return app


def _mk_user(found_app, email, created_at=None, **kw):
    from models import db, User
    u = User(email=email, is_guest=False, **kw)
    db.session.add(u)
    db.session.commit()
    if created_at is not None:
        u.created_at = created_at
        db.session.commit()
    return u


def _grant(found_app, user_id, starts=CUTOFF_NAIVE, ends=UNTIL_NAIVE, campaign='founders_2026_v1'):
    from models import db
    from models_founders import FounderGrant
    g = FounderGrant(user_id=user_id, campaign_id=campaign, amount=0, payment_id=None,
                     is_free_grant=True, starts_at=starts, expires_at=ends,
                     granted_by='test', grant_batch=1)
    db.session.add(g)
    db.session.commit()
    return g


def _sub(found_app, user_id, starts, ends, payment_id='pay_x', beta=False, plan='premium_monthly'):
    from models import db
    from services.subscription import get_subscription_service
    get_subscription_service().activate_premium(
        user_id, plan=plan, payment_id=payment_id, is_beta=beta, amount_rub=490,
        starts_at=starts, expires_at=ends)
    db.session.commit()


def _args(**kw):
    d = dict(apply=False, rollback=False, campaign_id='founders_2026_v1',
             batch_size=500, limit=0)
    d.update(kw)
    return argparse.Namespace(**d)


# ─────────────────────────── граница Основателя ───────────────────────────

def test_cutoff_is_02nov2100utc(found_app):
    """users.created_at — naive UTC: граница 02.11 23:59:59 МСК = 02.11 20:59:59 UTC."""
    assert founder_cutoff() == datetime(2026, 11, 2, 21, 0, tzinfo=timezone.utc)
    u_before = _mk_user(found_app, 'a@x.invalid', created_at=datetime(2026, 11, 2, 20, 59, 59))
    u_at = _mk_user(found_app, 'b@x.invalid', created_at=datetime(2026, 11, 2, 21, 0, 0))
    import scripts.grant_founders as gf
    from models import User
    q = gf._eligible_filter(User, founder_cutoff(), set())
    ids = [u.id for u in q.all()]
    assert u_before.id in ids and u_at.id not in ids


# ─────────────────────────── dry-run / apply ───────────────────────────

def test_dry_run_writes_nothing(found_app, monkeypatch):
    from models import User
    from models_founders import FounderGrant
    import scripts.grant_founders as gf
    _mk_user(found_app, 'founder1@x.invalid', created_at=datetime(2026, 9, 1))
    rc = gf._run(found_app.extensions and __import__('models').db, User, FounderGrant,
                 _args(), founder_cutoff(), founder_cutoff(), founder_grant_until())
    assert rc == 0
    assert User.query.filter(User.is_founder == True).count() == 0      # noqa: E712
    assert FounderGrant.query.count() == 0


def test_early_apply_forbidden(found_app):
    from models import User
    from models_founders import FounderGrant
    import scripts.grant_founders as gf
    _mk_user(found_app, 'early@x.invalid', created_at=datetime(2026, 9, 1))
    before_cutoff = datetime(2026, 10, 30, 12, 0)
    rc = gf._run(__import__('models').db, User, FounderGrant,
                 _args(apply=True), founder_cutoff(), founder_cutoff(), founder_grant_until(),
                 now=before_cutoff)
    assert rc == 2
    assert FounderGrant.query.count() == 0


def test_apply_grants_and_is_idempotent(found_app):
    from models import User
    from models_founders import FounderGrant
    import scripts.grant_founders as gf
    u = _mk_user(found_app, 'founder2@x.invalid', created_at=datetime(2026, 9, 1))
    rc = gf._run(__import__('models').db, User, FounderGrant,
                 _args(apply=True), founder_cutoff(), founder_cutoff(), founder_grant_until(),
                 now=NOW_LAUNCH.replace(tzinfo=None))
    assert rc == 0
    assert u.is_founder and u.founder_price_eligible and u.founder_granted_at is not None
    grants = FounderGrant.query.filter_by(user_id=u.id).all()
    assert len(grants) == 1
    g = grants[0]
    assert g.amount == 0 and g.payment_id is None and g.is_free_grant is True
    assert g.starts_at == CUTOFF_NAIVE and g.expires_at == UNTIL_NAIVE

    # повторный запуск — ничего не дублируется
    rc = gf._run(__import__('models').db, User, FounderGrant,
                 _args(apply=True), founder_cutoff(), founder_cutoff(), founder_grant_until(),
                 now=NOW_LAUNCH.replace(tzinfo=None))
    assert rc == 0
    assert FounderGrant.query.filter_by(user_id=u.id).count() == 1
    from models import db
    u2 = db.session.get(User, u.id)
    assert u2.is_founder


def test_resume_after_failure_completes(found_app, monkeypatch):
    """Сбой в середине пачки → повторный запуск довыдаёт всё (идемпотентность)."""
    from models import User
    from models_founders import FounderGrant
    import scripts.grant_founders as gf
    from models import db
    for i in range(6):
        _mk_user(found_app, f'resume{i}@x.invalid', created_at=datetime(2026, 8, 1))
    calls = {'n': 0}
    orig_commit = db.session.commit

    def flaky_commit():
        calls['n'] += 1
        if calls['n'] == 2:   # падаем на первом же коммите пачки
            raise RuntimeError('db gone')
        return orig_commit()
    monkeypatch.setattr(db.session, 'commit', flaky_commit)
    with pytest.raises(RuntimeError):
        gf._run(db, User, FounderGrant, _args(apply=True, batch_size=5),
                founder_cutoff(), founder_cutoff(), founder_grant_until(),
                now=NOW_LAUNCH.replace(tzinfo=None))
    monkeypatch.setattr(db.session, 'commit', orig_commit)
    db.session.rollback()
    rc = gf._run(db, User, FounderGrant, _args(apply=True, batch_size=5),
                 founder_cutoff(), founder_cutoff(), founder_grant_until(),
                 now=NOW_LAUNCH.replace(tzinfo=None))
    assert rc == 0
    assert FounderGrant.query.count() == 6
    assert User.query.filter(User.is_founder == True).count() == 6  # noqa: E712


def test_paying_user_keeps_paid_period(found_app):
    """Уже платящий: получает флаги и выдачу, оплаченный срок не меняется."""
    from models import User
    from models_founders import FounderGrant
    import scripts.grant_founders as gf
    from models import db
    u = _mk_user(found_app, 'payer@x.invalid', created_at=datetime(2026, 9, 1))
    paid_end = datetime(2027, 3, 1)
    _sub(found_app, u.id, datetime(2026, 11, 1), paid_end)
    rc = gf._run(db, User, FounderGrant, _args(apply=True),
                 founder_cutoff(), founder_cutoff(), founder_grant_until(),
                 now=NOW_LAUNCH.replace(tzinfo=None))
    assert rc == 0
    from sqlalchemy import text
    row = db.session.execute(text(
        "SELECT expires_at FROM subscriptions WHERE user_id=:u AND status='active'"),
        {'u': u.id}).first()
    assert str(row[0]).startswith('2027-03-01')       # оплаченный срок не тронут
    source, exp = resolve_access(db.session.get(User, u.id), now=NOW_LAUNCH)
    assert source == 'paid' and exp == datetime(2027, 3, 1, tzinfo=timezone.utc)


# ─────────────────────────── resolve_access ───────────────────────────

def test_priority_paid_founder_trial_free(found_app):
    from models import db, User
    # free
    u_free = _mk_user(found_app, 'free@x.invalid')
    assert resolve_access(u_free, now=NOW_LAUNCH) == ('free', None)
    # trial
    u_trial = _mk_user(found_app, 'trial@x.invalid', trial_until=datetime(2026, 11, 20))
    assert resolve_access(u_trial, now=NOW_LAUNCH)[0] == 'trial'
    # founder перекрывает trial (окно выдачи длиннее)
    _grant(found_app, u_trial.id)
    source, exp = resolve_access(u_trial, now=NOW_LAUNCH)
    assert source == 'founder' and exp == datetime(2027, 1, 31, 21, 0, tzinfo=timezone.utc)
    # paid перекрывает founder
    u_paid = _mk_user(found_app, 'paidf@x.invalid')
    _grant(found_app, u_paid.id)
    _sub(found_app, u_paid.id, datetime(2026, 11, 2), datetime(2026, 12, 2))
    source, exp = resolve_access(u_paid, now=NOW_LAUNCH)
    assert source == 'paid' and exp == datetime(2026, 12, 2, tzinfo=timezone.utc)


def test_trial_does_not_shorten_founder(found_app):
    """Триал с trial_until в декабре: resolve_access показывает 01.02.2027."""
    from models import db
    u = _mk_user(found_app, 'tf@x.invalid', trial_until=datetime(2026, 12, 15))
    _grant(found_app, u.id)
    source, exp = resolve_access(u, now=NOW_LAUNCH)
    assert source == 'founder'
    assert exp == datetime(2027, 1, 31, 21, 0, tzinfo=timezone.utc)


def test_grant_ends_exactly_feb1_msk(found_app):
    """Окончание ровно 01.02.2027 00:00 МСК (граница не включается)."""
    from models import db
    u = _mk_user(found_app, 'edge@x.invalid')
    _grant(found_app, u.id)
    at_end = datetime(2027, 1, 31, 21, 0, tzinfo=timezone.utc)
    just_before = at_end - timedelta(seconds=1)
    assert resolve_access(u, now=just_before)[0] == 'founder'
    assert resolve_access(u, now=at_end)[0] == 'free'   # в сам момент 01.02 00:00 доступа уже нет


def test_future_paid_row_not_active_early(found_app):
    """Будущая строка (год Основателя с 01.02.2027) не открывает доступ раньше starts_at."""
    from models import db
    u = _mk_user(found_app, 'future@x.invalid')
    _sub(found_app, u.id, datetime(2027, 2, 1), datetime(2028, 2, 1), payment_id='pay_year')
    assert resolve_access(u, now=NOW_LAUNCH)[0] == 'free'
    after = datetime(2027, 2, 2, tzinfo=timezone.utc)
    source, exp = resolve_access(u, now=after)
    assert source == 'paid' and exp == datetime(2028, 2, 1, tzinfo=timezone.utc)


def test_beta_subscription_is_not_paid(found_app):
    from models import db
    u = _mk_user(found_app, 'beta@x.invalid')
    _sub(found_app, u.id, datetime(2026, 11, 1), datetime(2026, 12, 1), beta=True)
    assert resolve_access(u, now=NOW_LAUNCH)[0] == 'free'


# ─────────────────────────── финансы и цены ───────────────────────────

def test_no_financial_events_from_grant(found_app):
    """Бесплатная выдача не создаёт orders и analytics_events."""
    from models import db, User
    from models_founders import FounderGrant
    import scripts.grant_founders as gf
    _mk_user(found_app, 'noev@x.invalid', created_at=datetime(2026, 9, 1))
    gf._run(db, User, FounderGrant, _args(apply=True), founder_cutoff(),
            founder_cutoff(), founder_grant_until(), now=NOW_LAUNCH.replace(tzinfo=None))
    from models_billing import Order, AnalyticsEvent
    assert Order.query.count() == 0 and AnalyticsEvent.query.count() == 0


def test_founder_prices(found_app):
    from services.billing.catalog import get_product, amount_for
    u_f = _mk_user(found_app, 'fp@x.invalid', is_founder=True, founder_price_eligible=True)
    u_n = _mk_user(found_app, 'np@x.invalid')
    assert amount_for(get_product('student_month'), u_f) == (39000, True)   # 390 ₽
    assert amount_for(get_product('student_year'), u_f) == (279000, True)  # 2 790 ₽
    assert amount_for(get_product('student_month'), u_n) == (49000, False)  # 490 ₽
    assert amount_for(get_product('student_year'), u_n) == (299000, False)  # 2 990 ₽


# ─────────────────────────── paywall ───────────────────────────

def test_paywall_uses_resolve_access(found_app, monkeypatch):
    """user_has_paid_access больше не пропускает всех (is_trial_active всегда True)."""
    from method_week.paywall import user_has_paid_access
    from models import db
    import services.access as access_mod
    _mk_user(found_app, 'pw_filler@x.invalid')   # чтобы тестовый user не был uid=1 (админ)
    u = _mk_user(found_app, 'pw@x.invalid')   # без доступа

    class _FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW_LAUNCH if tz else NOW_LAUNCH.replace(tzinfo=None)
    monkeypatch.setattr(access_mod, 'datetime', _FakeDT)
    assert user_has_paid_access(u) is False
    _grant(found_app, u.id)
    assert user_has_paid_access(u) is True


# ─────────────────────────── откат ───────────────────────────

def test_rollback_targeted(found_app):
    """Откат удаляет только выдачи кампании; платежи и оплаченные права не трогает."""
    from models import db, User
    from models_founders import FounderGrant
    import scripts.grant_founders as gf
    u1 = _mk_user(found_app, 'rb1@x.invalid', created_at=datetime(2026, 9, 1))
    _sub(found_app, u1.id, datetime(2026, 11, 1), datetime(2026, 12, 1))
    gf._run(db, User, FounderGrant, _args(apply=True), founder_cutoff(),
            founder_cutoff(), founder_grant_until(), now=NOW_LAUNCH.replace(tzinfo=None))
    assert FounderGrant.query.count() == 1
    rc = gf._rollback(db, User, FounderGrant, 'founders_2026_v1')
    assert rc == 0
    assert FounderGrant.query.count() == 0
    u1r = db.session.get(User, u1.id)
    assert u1r.is_founder is False and u1r.founder_price_eligible is False
    from sqlalchemy import text
    n_subs = db.session.execute(text(
        "SELECT COUNT(*) FROM subscriptions WHERE user_id=:u AND status='active'"),
        {'u': u1.id}).scalar()
    assert n_subs == 1                                 # оплаченный доступ не тронут
