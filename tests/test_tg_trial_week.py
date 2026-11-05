# -*- coding: utf-8 -*-
"""TG_TRIAL_WEEK — «Неделя Premium за подписку на Telegram-канал».

Запуск: pytest tests/test_tg_trial_week.py -q
Telegram Bot API замокан — сеть не нужна.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text


@pytest.fixture
def tg_app(app, monkeypatch):
    from models import db
    import models_tg_trial  # noqa: F401
    db.create_all()
    db.session.execute(text("""CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, plan TEXT NOT NULL DEFAULT 'free',
        status TEXT NOT NULL DEFAULT 'active', started_at TIMESTAMP, expires_at TIMESTAMP,
        payment_method TEXT, payment_id TEXT, amount_rub INTEGER, is_trial INTEGER DEFAULT 0,
        is_beta_access INTEGER DEFAULT 1, created_at TIMESTAMP)"""))
    db.session.commit()
    # id 1/5 — пилотные аккаунты (у них Premium и так); начинаем id с 100
    db.session.execute(text("INSERT INTO users (id, email, is_guest) VALUES (99, 'seed@x.ru', 0)"))
    db.session.commit()
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'test-token')
    monkeypatch.setenv('TG_TRIAL_CHANNEL', 'FormylaMaths')
    import services.subscription as sub
    monkeypatch.setattr(sub, '_service_instance', None)
    from services import tg_trial
    members = set()
    monkeypatch.setattr(tg_trial, 'check_membership', lambda tg_id: str(tg_id) in members)
    from routes.tg_trial import tg_trial_bp
    if 'tg_trial' not in app.blueprints:
        app.register_blueprint(tg_trial_bp)
    app.tg_members = members
    return app


def _user(email, tg_id=None, role='student'):
    from models import db, User
    u = User(email=email, is_guest=False, telegram_id=tg_id)
    try:
        u.role = role
    except Exception:
        pass
    db.session.add(u)
    db.session.commit()
    return u


def _active_subs(uid):
    from models import db
    return db.session.execute(text(
        "SELECT plan, expires_at, is_trial FROM subscriptions WHERE user_id=:u AND status='active'"),
        {'u': uid}).fetchall()


def test_week_granted_exactly_7_days(tg_app):
    from services import tg_trial
    u = _user('a@x.ru', tg_id='111')
    tg_app.tg_members.add('111')
    assert tg_trial.get_state(u)['state'] == 'available'
    before = datetime.utcnow()
    res = tg_trial.claim_week(u)
    exp = datetime.fromisoformat(res['expires_at'])
    assert timedelta(days=7) - timedelta(seconds=5) < exp - before <= timedelta(days=7, seconds=5)
    subs = _active_subs(u.id)
    assert len(subs) == 1 and subs[0][0] == 'premium_intense' and int(subs[0][2]) == 1
    assert tg_trial.get_state(u)['state'] == 'active'
    from services.pilot import has_premium_access
    assert has_premium_access(u)


def test_not_subscribed_refused(tg_app):
    from services import tg_trial
    u = _user('b@x.ru', tg_id='222')
    with pytest.raises(tg_trial.TgTrialError) as e:
        tg_trial.claim_week(u)
    assert e.value.code == 'not_member'
    assert _active_subs(u.id) == []


def test_only_once_per_account(tg_app):
    from services import tg_trial
    u = _user('c@x.ru', tg_id='333')
    tg_app.tg_members.add('333')
    tg_trial.claim_week(u)
    with pytest.raises(tg_trial.TgTrialError) as e:
        tg_trial.claim_week(u)
    assert e.value.code == 'already_active'


def test_only_once_per_telegram(tg_app):
    """Отвязал Telegram, привязал к новому аккаунту — вторую неделю не дадим."""
    from models import db
    from services import tg_trial
    u1 = _user('d1@x.ru', tg_id='444')
    tg_app.tg_members.add('444')
    tg_trial.claim_week(u1)
    u1.telegram_id = None
    db.session.commit()
    u2 = _user('d2@x.ru', tg_id='444')
    with pytest.raises(tg_trial.TgTrialError) as e:
        tg_trial.claim_week(u2)
    assert e.value.code == 'tg_used'


def test_unknown_telegram_asks_to_subscribe(tg_app):
    """Telegram не привязан и по личной ссылке ещё не вступал — просим подписаться."""
    from services import tg_trial
    u = _user('e@x.ru')
    st = tg_trial.get_state(u)
    assert st['state'] == 'available' and st['tg_linked'] is False
    with pytest.raises(tg_trial.TgTrialError) as e:
        tg_trial.claim_week(u)
    assert e.value.code == 'not_member'


def test_paid_premium_gets_plus_7_days(tg_app):
    from models import db
    from services import tg_trial
    u = _user('f@x.ru', tg_id='555')
    db.session.execute(text(
        "INSERT INTO subscriptions (user_id, plan, status, started_at, expires_at, payment_id, is_trial, is_beta_access)"
        " VALUES (:u, 'premium_intense', 'active', :s, :e, 'pay_1', 0, 0)"),
        {'u': u.id, 's': datetime.utcnow() - timedelta(days=1), 'e': datetime.utcnow() + timedelta(days=20)})
    db.session.commit()
    st = tg_trial.get_state(u)
    assert st['state'] == 'available' and st['has_premium'] is True
    tg_app.tg_members.add('555')
    res = tg_trial.claim_week(u)
    exp = datetime.fromisoformat(res['expires_at'])
    # +7 дней ПОСЛЕ оплаченного срока (20 дней), оплаченный период не сокращён
    assert timedelta(days=26, hours=23) < exp - datetime.utcnow() < timedelta(days=27, hours=1)
    subs = _active_subs(u.id)
    assert len(subs) == 2


def test_perpetual_premium_not_touched(tg_app):
    """Бессрочный Premium: подписку не трогаем, выдачу фиксируем (второй раз — нельзя)."""
    from models import db
    from services import tg_trial
    u = _user('perp@x.ru', tg_id='556')
    db.session.execute(text(
        "INSERT INTO subscriptions (user_id, plan, status, started_at, expires_at, is_trial)"
        " VALUES (:u, 'premium_intense', 'active', :s, NULL, 0)"), {'u': u.id, 's': datetime.utcnow()})
    db.session.commit()
    tg_app.tg_members.add('556')
    tg_trial.claim_week(u)
    assert len(_active_subs(u.id)) == 1
    assert tg_trial.get_state(u)['state'] == 'active'


def test_week_replaces_active_trial_day(tg_app):
    from models import db
    from services import tg_trial
    u = _user('g@x.ru', tg_id='666')
    tg_app.tg_members.add('666')
    db.session.execute(text(
        "INSERT INTO subscriptions (user_id, plan, status, started_at, expires_at, is_trial, is_beta_access)"
        " VALUES (:u, 'premium_intense', 'active', :s, :e, 1, 1)"),
        {'u': u.id, 's': datetime.utcnow(), 'e': datetime.utcnow() + timedelta(hours=20)})
    db.session.commit()
    assert tg_trial.get_state(u)['state'] == 'available'
    tg_trial.claim_week(u)
    subs = _active_subs(u.id)
    assert len(subs) == 1  # пробный день погашен, осталась неделя
    exp = subs[0][1]
    exp = exp if isinstance(exp, datetime) else datetime.fromisoformat(str(exp))
    assert exp - datetime.utcnow() > timedelta(days=6, hours=23)


def test_parent_hidden(tg_app):
    from services import tg_trial
    u = _user('h@x.ru', tg_id='777', role='parent')
    if getattr(u, 'role', 'student') != 'parent':
        pytest.skip('в модели нет роли')
    assert tg_trial.get_state(u)['state'] == 'hidden'


def test_claim_endpoint_with_csrf(tg_app):
    u = _user('i@x.ru', tg_id='888')
    tg_app.tg_members.add('888')
    c = tg_app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u.id)
        s['_fresh'] = True
        s['_csrf_token'] = 'tok'
    r = c.post('/api/tg-trial/claim', json={})
    assert r.status_code == 400 and r.get_json()['code'] == 'csrf'
    r = c.post('/api/tg-trial/claim', json={}, headers={'X-CSRF-Token': 'tok'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['ok'] is True
    r = c.get('/api/tg-trial/status')
    assert r.get_json()['state'] == 'active'


# ───────── интеграция: выбор 6 дней, первая (диагностическая) неделя, скорость ─────────

def test_week_requires_choosing_6_days(tg_app):
    """После выдачи недели гейт /schedule требует ровно 6 дней (как у «Работяги»)."""
    from services import tg_trial
    from services.schedule_days import days_for_plan, required_days_count, save_user_days
    from routes.schedule_days import _active_pilot_plan
    u = _user('s1@x.ru', tg_id='901')
    tg_app.tg_members.add('901')
    res = tg_trial.claim_week(u)
    assert res['needs_schedule'] is True and res['days_required'] == 6
    plan = _active_pilot_plan(u.id)
    assert plan == 'premium_intense' and required_days_count(plan) == 6
    assert days_for_plan(u.id, plan) is None            # гейт отправит на /schedule
    assert save_user_days(u.id, [0, 1, 2, 3, 4, 5], plan) is True
    assert days_for_plan(u.id, plan) == [0, 1, 2, 3, 4, 5]
    assert save_user_days(u.id, [0, 1, 2], plan) is False   # не 6 — нельзя


def test_week_is_diagnostic_week_with_5_test_tasks(tg_app):
    """Неделя = неделя 1 Premium: диагностика (тест 5 задач) + задачи дня."""
    from services import tg_trial
    from services.theme_probe import PROBE_SIZE
    from services.pilot import can_take_theme_test
    from curator.session_plan import _pilot_variant
    u = _user('s2@x.ru', tg_id='902')
    tg_app.tg_members.add('902')
    assert not can_take_theme_test(u)                    # до недели тест закрыт
    tg_trial.claim_week(u)
    assert PROBE_SIZE == 5
    assert can_take_theme_test(u)                        # с неделей — открыт
    assert _pilot_variant(u.id) == 'premium_intense'
    sub = _active_subs(u.id)[0]
    exp = sub[1] if isinstance(sub[1], datetime) else datetime.fromisoformat(str(sub[1]))
    # вся неделя укладывается в days_in//7 + 1 == 1 (диагностическая неделя)
    assert (exp - datetime.utcnow()).days < 7


def test_get_state_is_cheap(tg_app):
    """Состояние для баннера — не больше 3 SQL-запросов, повторный вызов — 0."""
    from models import db
    from sqlalchemy import event
    from services import tg_trial
    u = _user('s3@x.ru', tg_id='903')
    n = {'q': 0}

    def _count(conn, cur, stmt, params, ctx, many):
        n['q'] += 1
    event.listen(db.engine, 'before_cursor_execute', _count)
    try:
        tg_trial._drop_cache()
        tg_trial.get_state(u)
        first = n['q']
        tg_trial.get_state(u)
        assert n['q'] == first                           # из кэша запроса
        assert first <= 3, first
    finally:
        event.remove(db.engine, 'before_cursor_execute', _count)


def test_state_fresh_after_claim(tg_app):
    from services import tg_trial
    u = _user('s4@x.ru', tg_id='904')
    tg_app.tg_members.add('904')
    assert tg_trial.get_state(u)['state'] == 'available'
    tg_trial.claim_week(u)
    assert tg_trial.get_state(u)['state'] == 'active'    # кэш сброшен выдачей


def test_check_membership_uses_api_base(monkeypatch):
    """TELEGRAM_API_BASE перенаправляет запросы к Bot API на прокси."""
    from services import tg_trial

    seen = {}

    class _Resp:
        def json(self):
            return {'ok': True, 'result': {'status': 'member'}}

    def fake_get(url, params=None, timeout=None):
        seen['url'] = url
        return _Resp()

    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', '123:abc')
    monkeypatch.setenv('TELEGRAM_API_BASE', 'https://tgapi.example.org/')
    monkeypatch.setattr(tg_trial.requests, 'get', fake_get)
    assert tg_trial.check_membership('42') is True
    assert seen['url'] == 'https://tgapi.example.org/bot123:abc/getChatMember'

    monkeypatch.delenv('TELEGRAM_API_BASE')
    tg_trial.check_membership('42')
    assert seen['url'].startswith('https://api.telegram.org/bot')


class _FakeBot:
    """Мини-Bot API: createChatInviteLink / getUpdates / sendMessage."""

    def __init__(self):
        self.updates, self.sent, self.n = [], [], 0

    def __call__(self, method, payload, timeout=6):
        if method == 'createChatInviteLink':
            self.n += 1
            return {'invite_link': f'https://t.me/+inv{self.n}'}
        if method == 'getUpdates':
            off = payload.get('offset') or 0
            assert 'chat_member' in payload['allowed_updates']
            return [u for u in self.updates if u['update_id'] >= off]
        if method == 'sendMessage':
            self.sent.append(payload)
            return {}
        raise AssertionError(method)

    def join(self, link, tg_id):
        self.updates.append({'update_id': 100 + len(self.updates), 'chat_member': {
            'chat': {'id': -1001, 'username': 'FormylaMaths', 'type': 'channel'},
            'from': {'id': int(tg_id)},
            'old_chat_member': {'status': 'left', 'user': {'id': int(tg_id)}},
            'new_chat_member': {'status': 'member', 'user': {'id': int(tg_id)}},
            'invite_link': {'invite_link': link, 'name': 'x'}}})

    def start(self, token, tg_id):
        self.updates.append({'update_id': 100 + len(self.updates), 'message': {
            'message_id': 1, 'chat': {'id': int(tg_id), 'type': 'private'},
            'from': {'id': int(tg_id)}, 'text': f'/start {token}'}})


@pytest.fixture
def fake_bot(tg_app, monkeypatch):
    from services import tg_trial
    bot = _FakeBot()
    monkeypatch.setattr(tg_trial, '_bot_call', bot)
    monkeypatch.setenv('TELEGRAM_BOT_USERNAME', 'formyla_poster_bot')
    return bot


def test_subscribe_by_personal_link_then_check(tg_app, fake_bot):
    """Перешёл по личной ссылке, подписался, вернулся, нажал «Проверить» — неделя выдана."""
    from services import tg_trial
    u = _user('inv@x.ru')
    links = tg_trial.get_links(u)
    assert links['invite_link'] == 'https://t.me/+inv1'
    assert links['bot_link'].startswith('https://t.me/formyla_poster_bot?start=fw')
    assert tg_trial.get_links(u)['invite_link'] == 'https://t.me/+inv1'   # ссылка одна на пользователя
    other = _user('other@x.ru')
    tg_trial.get_links(other)                                             # +inv2 — чужая
    fake_bot.join('https://t.me/+inv2', 999)                              # чужой вступил — не наш
    fake_bot.join('https://t.me/+inv1', 5551)
    tg_app.tg_members.add('5551')
    res = tg_trial.claim_week(u)
    assert res['expires_at']
    assert tg_trial.get_state(u)['state'] == 'active'
    assert u.telegram_id == '5551'          # Telegram запомнили в аккаунте
    from models_tg_trial import TgBotCursor
    from models import db
    assert db.session.get(TgBotCursor, 1).offset == 102


def test_already_subscribed_confirms_via_bot(tg_app, fake_bot):
    """Уже был подписан: «Подтвердить через бота» (/start <token>) → проверка проходит."""
    from services import tg_trial
    u = _user('old@x.ru')
    token = tg_trial.get_links(u)['bot_link'].split('start=')[1]
    fake_bot.start(token, 7771)
    tg_app.tg_members.add('7771')
    tg_trial.claim_week(u)
    assert tg_trial.get_state(u)['state'] == 'active'
    assert fake_bot.sent and fake_bot.sent[0]['chat_id'] == 7771


def test_joined_but_left_is_refused(tg_app, fake_bot):
    """Вступил по ссылке и сразу отписался — getChatMember не подтвердит, недели нет."""
    from services import tg_trial
    u = _user('left@x.ru')
    fake_bot.join(tg_trial.get_links(u)['invite_link'], 8881)
    with pytest.raises(tg_trial.TgTrialError) as e:
        tg_trial.claim_week(u)
    assert e.value.code == 'not_member'


def test_link_endpoint(tg_app, fake_bot):
    u = _user('ep@x.ru')
    client = tg_app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(u.id)
        sess['_fresh'] = True
    r = client.get('/api/tg-trial/link')
    assert r.status_code == 200, r.data
    assert r.get_json()['invite_link'].startswith('https://t.me/+inv')


def _render_promo(app, user, qs=''):
    """Отрендерить партиал окна от имени user (контекст-процессора в тестовом app нет)."""
    from flask import render_template
    from flask_login import login_user
    from services import tg_trial
    with app.test_request_context('/daily_tasks' + qs):
        login_user(user)
        return render_template('partials/tg_trial_week.html', is_free_user=False,
                               tg_trial_state=lambda: tg_trial.get_state(user),
                               csrf_token=lambda: 'x')


def test_admin_preview_shows_window(tg_app):
    """Админ (id 1) по ?tg_week=preview видит окно с пометкой «Предпросмотр»."""
    from models import db, User
    admin = db.session.get(User, 1) or User(id=1, email='admin@x.ru', is_guest=False)
    db.session.add(admin)
    db.session.commit()
    html = _render_promo(tg_app, admin, '?tg_week=preview')
    assert 'Предпросмотр для админа' in html and 'Проверить подписку' in html
    assert 'var PREVIEW = true' in html
    plain = _render_promo(tg_app, admin)
    assert 'tgtModal' in plain and 'var PREVIEW = false' in plain   # акция видна всем, без пометки


def test_preview_param_ignored_for_regular_user(tg_app):
    """Обычному пользователю ?tg_week=preview не включает режим предпросмотра:
    окно настоящее (с Premium — «+7 дней»)."""
    from models import db
    u = _user('prem@x.ru', tg_id='321')
    db.session.execute(text(
        "INSERT INTO subscriptions (user_id, plan, status, expires_at, is_trial) "
        "VALUES (:u, 'premium_intense', 'active', :e, 0)"),
        {'u': u.id, 'e': (datetime.utcnow() + timedelta(days=30)).isoformat(sep=' ')})
    db.session.commit()
    html = _render_promo(tg_app, u, '?tg_week=preview')
    assert 'var PREVIEW = false' in html and 'Предпросмотр для админа' not in html
    assert '+7 дней Premium' in html
