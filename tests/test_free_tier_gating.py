# -*- coding: utf-8 -*-
"""FREE_TIER_V2 (28.10.2026): бесплатная версия = 1 задача в день,
закрытые разделы (тест/методы/генератор/ИИ-тьютор) с сообщением
«недоступно в бесплатной версии».

Запуск: pytest tests/test_free_tier_gating.py -q
"""
from datetime import date

import pytest

import services.limits as limits


@pytest.fixture
def free_tier_app(app, monkeypatch):
    """Paywall и лимиты включены — как в проде с 28.10.2026."""
    monkeypatch.setenv('PAYWALL_ENABLED', '1')
    monkeypatch.setenv('PAYWALL_START_DATE', '2026-10-01')
    monkeypatch.setenv('PAYWALL_MODE', 'rollout')
    monkeypatch.setenv('FREE_LIMITS_DISABLED', '0')
    monkeypatch.delenv('FREE_TASKS_PER_DAY', raising=False)
    monkeypatch.delenv('FREE_AI_PER_DAY', raising=False)
    from models import db
    from sqlalchemy import text
    db.create_all()
    pg = db.engine.dialect.name == 'postgresql'
    serial = 'SERIAL PRIMARY KEY' if pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    for ddl in (
        f"""CREATE TABLE IF NOT EXISTS usage_daily (
            id {serial}, user_id INTEGER NOT NULL,
            date TEXT NOT NULL, tasks_completed INTEGER DEFAULT 0,
            ai_explanations_used INTEGER DEFAULT 0, tokens_consumed INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0)""",
        f"""CREATE TABLE IF NOT EXISTS subscriptions (
            id {serial}, user_id INTEGER NOT NULL, plan TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active', started_at TIMESTAMP, expires_at TIMESTAMP,
            payment_method TEXT, payment_id TEXT, amount_rub INTEGER, is_trial INTEGER DEFAULT 0,
            is_beta_access INTEGER DEFAULT 1, created_at TIMESTAMP)""",
    ):
        db.session.execute(text(ddl))
    db.session.commit()
    # В тестовом приложении method_week._install уже «израсходован» глобальным
    # флагом при импорте основного app (record_once срабатывает один раз),
    # поэтому guard paywall вешаем на тестовый app явно.
    from method_week.paywall import install_paywall
    install_paywall(app)
    return app


def _mk_user(appl, email, **kw):
    from models import db, User
    u = User(email=email, is_guest=False, **kw)
    db.session.add(u)
    db.session.commit()
    return u


def _mk_root(appl):
    """Первый пользователь базы (id=1 = админ в paywall) — чтобы тестовые
    «бесплатники» получали id >= 2 и не обходили paywall как админы."""
    from models import db, User
    existing = db.session.get(User, 1)
    if existing is None:
        db.session.add(User(email='root@x.invalid', is_guest=False))
        db.session.commit()
        existing = db.session.get(User, 1)
    return existing


def _client(appl, user):
    c = appl.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id)
    return c


# ─────────────────────────── дефолты ───────────────────────────

def test_free_limit_default_is_one_task():
    """Без env бесплатная версия = 1 задача в день (FREE_TIER_V2)."""
    import os
    saved = os.environ.pop('FREE_TASKS_PER_DAY', None)
    try:
        assert limits.free_tasks_per_day() == 1
    finally:
        if saved is not None:
            os.environ['FREE_TASKS_PER_DAY'] = saved


def test_paywall_active_by_default():
    """Paywall включён по умолчанию (PAYWALL_ENABLED не задан)."""
    import os
    saved = os.environ.pop('PAYWALL_ENABLED', None)
    saved_date = os.environ.pop('PAYWALL_START_DATE', None)
    try:
        from method_week.paywall import paywall_active
        assert paywall_active(today=date(2026, 10, 28)) is True
    finally:
        if saved is not None:
            os.environ['PAYWALL_ENABLED'] = saved
        if saved_date is not None:
            os.environ['PAYWALL_START_DATE'] = saved_date


# ─────────────────────────── закрытые разделы ───────────────────────────

def test_free_user_redirected_to_subscribe(free_tier_app):
    """Бесплатник на /probniks → редирект на /subscribe с названием раздела."""
    _mk_root(free_tier_app)
    u = _mk_user(free_tier_app, 'gate1@x.invalid')
    assert u.id != 1
    c = _client(free_tier_app, u)
    r = c.get('/probniks')
    assert r.status_code == 302
    loc = r.headers.get('Location', '')
    assert '/subscribe' in loc
    assert 'from=/probniks' in loc
    assert 'feature=' in loc


def test_free_user_json_gets_402(free_tier_app):
    """JSON-запрос к платному разделу → 402 + «недоступен в бесплатной версии»."""
    _mk_root(free_tier_app)
    u = _mk_user(free_tier_app, 'gate2@x.invalid')
    c = _client(free_tier_app, u)
    r = c.get('/probniks', headers={'Accept': 'application/json'})
    assert r.status_code == 402
    body = r.get_json()
    assert 'недоступен в бесплатной версии' in body.get('message', '')
    assert body.get('error') == 'payment_required'


def test_methods_catalog_gated(free_tier_app):
    """Каталог методов закрыт для бесплатных."""
    _mk_root(free_tier_app)
    u = _mk_user(free_tier_app, 'gate3@x.invalid')
    c = _client(free_tier_app, u)
    assert c.get('/olympiads/methods').status_code == 302


def test_daily_tasks_stay_open_for_free(free_tier_app):
    """Задачи дня НЕ закрыты paywall'ом: бесплатник видит страницу."""
    _mk_root(free_tier_app)
    u = _mk_user(free_tier_app, 'gate4@x.invalid')
    c = _client(free_tier_app, u)
    r = c.get('/daily_tasks/')
    assert r.status_code != 302 or '/subscribe' not in r.headers.get('Location', '')


def test_premium_user_passes_paywall(free_tier_app):
    """Premium-подписчик проходит paywall без редиректа."""
    _mk_root(free_tier_app)
    from datetime import datetime
    from models import db
    from services.subscription import get_subscription_service
    u = _mk_user(free_tier_app, 'gate5@x.invalid')
    get_subscription_service().activate_premium(
        u.id, payment_id='ft1', is_beta=False, amount_rub=490,
        starts_at=datetime(2026, 10, 1), expires_at=datetime(2026, 12, 1))
    db.session.commit()
    c = _client(free_tier_app, u)
    assert c.get('/probniks').status_code == 200


def test_admin_bypasses_paywall(free_tier_app):
    """uid=1 (админ) проходит paywall."""
    u = _mk_root(free_tier_app)
    c = _client(free_tier_app, u)
    assert c.get('/probniks').status_code == 200


# ─────────────────────────── лимит задач дня ───────────────────────────

def test_real_app_auto_attaches_paywall():
    """Импорт основного app регистрирует guard paywall автоматически
    (через daily_tasks_bp → method_week attach → install_paywall)."""
    import app as appmod
    funcs = [f.__name__ for f in appmod.app.before_request_funcs.get(None, [])]
    assert '_paywall_guard' in funcs


def test_free_user_gets_one_task_per_day(free_tier_app):
    """Фактическая выдача: бесплатнику резервируется РОВНО 1 задача,
    повторное открытие не расходует больше."""
    _mk_root(free_tier_app)
    u = _mk_user(free_tier_app, 'one@x.invalid')
    c = _client(free_tier_app, u)
    r1 = c.get('/daily_tasks/')
    ctx1 = limits.daily_context(u)
    assert ctx1['tasks_limit'] == 1
    # сколько бы ни происходило при первом открытии — не больше 1 задачи
    used1 = ctx1['tasks_limit'] - ctx1['tasks_remaining']
    assert used1 <= 1
    # повторное открытие того же набора не расходует лимит
    c.get('/daily_tasks/')
    ctx2 = limits.daily_context(u)
    used2 = ctx2['tasks_limit'] - ctx2['tasks_remaining']
    assert used2 == used1


def test_daily_tasks_limit_screen_one_task(free_tier_app):
    """После 1 решённой задачи бесплатник видит экран лимита (не редирект)."""
    _mk_root(free_tier_app)
    u = _mk_user(free_tier_app, 'gate7@x.invalid')
    day = limits.usage_date()
    assert limits.try_consume(u.id, 'free_tasks', 1, n=1, day=day) is True
    c = _client(free_tier_app, u)
    r = c.get('/daily_tasks/')
    txt = r.get_data(as_text=True)
    assert r.status_code == 402
    assert 'Дневной лимит' in txt
    # сообщение отражает текущий лимит — 1 задача
    assert '1 задача' in txt


# ─────────────────────────── FREE_TIER_UPSELL: бейджи Premium ───────────────────────────

def _badge_app(is_free):
    """Мини-приложение с настоящими шаблонами: рендерит partial бейджа
    с is_free_user из context processor (как в реальном app)."""
    import os
    from flask import Flask, render_template
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    a = Flask('badge_test', template_folder=os.path.join(here, 'templates'))

    @a.context_processor
    def _ctx():
        return {'is_free_user': is_free}

    @a.route('/badge')
    def badge():
        return render_template('partials/premium_badge.html', feature='ИИ-тьютор')
    return a


def test_premium_badge_visible_for_free_user():
    """Бейдж «🔒 Premium» показывается бесплатнику и ведёт на /subscribe."""
    c = _badge_app(is_free=True).test_client()
    txt = c.get('/badge').get_data(as_text=True)
    assert '🔒 Premium' in txt
    assert '/subscribe?feature=' in txt


def test_premium_badge_hidden_for_paid_user():
    """Premium-подписчик бейдж НЕ видит."""
    c = _badge_app(is_free=False).test_client()
    txt = c.get('/badge').get_data(as_text=True)
    assert '🔒 Premium' not in txt
    assert 'pm-upsell-badge' not in txt


def test_olymp_tutor_api_gated(free_tier_app):
    """ИИ-тьютор олимпиадного каталога (JSON API) закрыт для бесплатников: 402."""
    _mk_root(free_tier_app)
    u = _mk_user(free_tier_app, 'upsell3@x.invalid')
    c = _client(free_tier_app, u)
    r = c.get('/olymp-catalog/api/tutor/prepare',
              headers={'Accept': 'application/json'})
    assert r.status_code == 402
    body = r.get_json()
    assert body.get('error') == 'payment_required'
    assert 'недоступен' in body.get('message', '')


def test_olymp_task_template_parses(free_tier_app):
    """Регрессия: CSS шаблона задачи каталога содержит «){#…» — Jinja считал
    это началом комментария и страница падала с 500. Шаблон должен парситься."""
    free_tier_app.jinja_env.get_template('olymp_catalog/task.html')


def test_context_processor_is_free_user(monkeypatch):
    """Настоящий _inject_subscription_flags: бесплатник — True,
    платный (Premium/триал/founder) — False."""
    import app as appmod
    import method_week.paywall as pw
    import services.pilot as pilot_mod

    class FakeUser:
        is_authenticated = True
        current_plan = 'free'
        id = 42

    monkeypatch.setattr(appmod, 'current_user', FakeUser(), raising=False)
    monkeypatch.setattr(pilot_mod, 'is_pilot_user', lambda u: False)
    # бесплатник: платного доступа нет
    monkeypatch.setattr(pw, 'user_has_paid_access', lambda u: False)
    ctx = appmod._inject_subscription_flags()
    assert ctx.get('is_free_user') is True
    # платный доступ (Premium/триал/founder) — бейджи не показываем
    monkeypatch.setattr(pw, 'user_has_paid_access', lambda u: True)
    ctx = appmod._inject_subscription_flags()
    assert ctx.get('is_free_user') is False
