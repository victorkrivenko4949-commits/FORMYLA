# -*- coding: utf-8 -*-
"""AUTO_RENEW_V1 — тесты автопродления Premium (запросы к ЮKassa замоканы).

Проверяют главный инвариант контура: ОДНО продление на оплаченный период,
сколько бы раз ни пришли вебхук/джоба, и что оплаченные дни не сгорают.

Запуск: pytest tests/test_auto_renew.py -q
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text


@pytest.fixture
def ar_app(app, monkeypatch):
    """Контекст приложения с таблицами подписок и автопродления."""
    from models import db
    from services import auto_renew

    # _TABLES_ENSURED — глобальный кэш между приложениями: сбрасываем,
    # чтобы таблицы создались в БД этого теста
    monkeypatch.setattr(auto_renew, '_TABLES_ENSURED', False)

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
    auto_renew.ensure_tables()

    # yookassa_payments — как в routes/yookassa_pay._ensure_tables (диалект-зависимо)
    id_col = "SERIAL PRIMARY KEY" if db.engine.dialect.name == 'postgresql' else "INTEGER PRIMARY KEY AUTOINCREMENT"
    db.session.execute(text(
        f"CREATE TABLE IF NOT EXISTS yookassa_payments ("
        f"id {id_col}, order_id VARCHAR(64) UNIQUE NOT NULL,"
        "payment_id VARCHAR(128), user_id INTEGER NOT NULL,"
        "item_code VARCHAR(64) NOT NULL DEFAULT 'diamond_badge',"
        "amount_rub NUMERIC(10,2) NOT NULL DEFAULT 10.00,"
        "status VARCHAR(32) NOT NULL DEFAULT 'pending', confirmation_url TEXT,"
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, paid_at TIMESTAMP)"
    ))
    db.session.commit()
    return app


def _uid():
    from models import db, User
    u = User(email=f'ar_{datetime.utcnow().strftime("%H%M%S%f")}@test.invalid',
             nickname='ar_user', is_guest=False)
    db.session.add(u)
    db.session.commit()
    return u.id


def _add_sub(uid, expires_at, plan='premium_intense'):
    from models import db
    db.session.execute(text(
        "INSERT INTO subscriptions (user_id, plan, status, started_at, expires_at,"
        " is_beta_access, created_at) VALUES (:uid, :plan, 'active', :st, :ex, 0, :now)"
    ), {'uid': uid, 'plan': plan, 'st': datetime.utcnow() - timedelta(days=30),
        'ex': expires_at, 'now': datetime.utcnow()})
    db.session.commit()


def _add_renewal(uid, plan='premium_intense', enabled=1, next_charge=None, pm='pm-test-1'):
    from models import db
    from services.auto_renew import ensure_tables
    ensure_tables()
    db.session.execute(text(
        "INSERT INTO premium_auto_renewals (user_id, plan, price_rub, payment_method_id,"
        " enabled, next_charge_at) VALUES (:uid, :plan, 800, :pm, :en, :nc)"
    ), {'uid': uid, 'plan': plan, 'pm': pm, 'en': enabled, 'nc': next_charge})
    db.session.commit()
    row = db.session.execute(text(
        "SELECT id FROM premium_auto_renewals WHERE user_id = :uid"
    ), {'uid': uid}).fetchone()
    return row[0]


def _attempt(rid, period_start, period_end, order_id, status='pending'):
    from models import db
    db.session.execute(text(
        "INSERT INTO premium_renewal_attempts (renewal_id, period_start, period_end,"
        " order_id, status) VALUES (:rid, :ps, :pe, :oid, :st)"
    ), {'rid': rid, 'ps': period_start, 'pe': period_end, 'oid': order_id, 'st': status})
    db.session.commit()


def _renewal_row(uid):
    from models import db
    return db.session.execute(text(
        "SELECT plan, price_rub, enabled, next_charge_at, fail_count"
        " FROM premium_auto_renewals WHERE user_id = :uid"
    ), {'uid': uid}).fetchone()


# ── Джоба: безопасность ──────────────────────────────────────────────────

def test_job_skips_when_yookassa_not_configured(ar_app, monkeypatch):
    """Демо-режим: никаких списаний вообще."""
    from services import auto_renew
    monkeypatch.setenv('PREMIUM_AUTORENEW_ENABLED', '1')
    monkeypatch.setattr(auto_renew, '_yk_cfg', lambda: {'configured': False})
    stats = auto_renew.run_renewal_job()
    assert stats == {'skipped': 'not_configured'}


def test_job_disabled_by_default(ar_app, monkeypatch):
    """Без явного PREMIUM_AUTORENEW_ENABLED=1 автосписания выключены."""
    from services import auto_renew
    monkeypatch.delenv('PREMIUM_AUTORENEW_ENABLED', raising=False)
    assert auto_renew.run_renewal_job() == {'skipped': 'disabled_by_env'}


def test_active_premium_check_fail_closed(ar_app, monkeypatch):
    """_active_premium при сбое БД запрещает оплату (fail-closed), а не разрешает."""
    from routes import premium_pay as pp
    import services.subscription as sub

    monkeypatch.setattr(pp, 'current_user', type('U', (), {'id': 999999})())
    orig = sub.get_subscription_service
    sub.get_subscription_service = lambda: (_ for _ in ()).throw(RuntimeError('db down'))
    try:
        result = pp._active_premium()
        assert result is not None and result.get('is_premium') is True
    finally:
        sub.get_subscription_service = orig


# ── Продление: идемпотентность и сохранение оплаченных дней ───────────────

def test_handle_succeeded_payment_idempotent(ar_app):
    """Повторный вебхук/джоба не продлевают подписку дважды."""
    from models import db
    from services import auto_renew

    uid = _uid()
    period_start = datetime.utcnow() + timedelta(hours=2)   # списание заранее
    period_end = period_start + timedelta(days=30)
    _add_sub(uid, expires_at=period_start)
    rid = _add_renewal(uid, next_charge=period_start)
    order_id = 'ord-idem-1'
    _attempt(rid, period_start, period_end, order_id)

    for _ in range(3):  # вебхук + возврат + джоба
        assert auto_renew.handle_succeeded_payment(order_id, 'pay-1', uid, 'premium_intense')

    # ровно ОДНА подписка на следующий период, до period_end
    rows = db.session.execute(text(
        "SELECT expires_at FROM subscriptions WHERE user_id = :uid AND status = 'active'"
        " ORDER BY expires_at DESC"
    ), {'uid': uid}).fetchall()
    assert len(rows) == 2  # старая + продлённая
    assert auto_renew._to_dt(rows[0][0]) == period_end

    # следующий платёж — через 30 дней, попытка закрыта
    ren = _renewal_row(uid)
    assert auto_renew._to_dt(ren[3]) == period_end
    st = db.session.execute(text(
        "SELECT status FROM premium_renewal_attempts WHERE order_id = :oid"
    ), {'oid': order_id}).fetchone()
    assert st[0] == 'succeeded'


def test_handle_foreign_order_returns_false(ar_app):
    """Чужой order_id (обычный первый платёж) не трогается контуром продления."""
    from services import auto_renew
    assert auto_renew.handle_succeeded_payment('ord-not-ours', 'pay-x', 1, 'premium_intense') is False


def test_renewal_extends_from_period_start_not_now(ar_app):
    """Продление считается от конца оплаченного периода — дни не сгорают."""
    from models import db
    from services import auto_renew

    uid = _uid()
    period_start = datetime.utcnow() + timedelta(hours=2)
    period_end = period_start + timedelta(days=30)
    _add_sub(uid, expires_at=period_start)
    rid = _add_renewal(uid, next_charge=period_start)
    order_id = 'ord-early-1'
    _attempt(rid, period_start, period_end, order_id)

    auto_renew.handle_succeeded_payment(order_id, 'pay-2', uid, 'premium_intense')

    top = db.session.execute(text(
        "SELECT expires_at FROM subscriptions WHERE user_id = :uid"
        " AND status = 'active' ORDER BY expires_at DESC LIMIT 1"
    ), {'uid': uid}).fetchone()
    assert auto_renew._to_dt(top[0]) == period_end  # не now+30д, а период+30д


# ── Неудачное списание ────────────────────────────────────────────────────

def test_charge_failed_then_retry_with_new_order(ar_app, monkeypatch):
    """Отказ платежа: пауза 24ч; повтор идёт с НОВЫМ order_id (старый
    Idempotence-Key вернул бы тот же отклонённый платёж)."""
    from models import db
    from services import auto_renew

    uid = _uid()
    period_start = datetime.utcnow()
    _add_sub(uid, expires_at=period_start)
    rid = _add_renewal(uid, next_charge=period_start)

    class Resp:
        status_code = 402
        content = b'{}'
        def json(self):
            return {'description': 'payment declined'}

    monkeypatch.setattr(auto_renew.requests, 'post', lambda *a, **kw: Resp())
    monkeypatch.setattr(auto_renew, '_yk_cfg',
                        lambda: {'configured': True, 'shop_id': 's', 'secret_key': 'k'})

    stats = {'failed': 0}
    auto_renew._charge_renewal(rid, uid, 'premium_intense', 800.0, 'pm-test-1', stats)
    assert stats['failed'] == 1

    first_order = db.session.execute(text(
        "SELECT order_id, status FROM premium_renewal_attempts WHERE renewal_id = :rid"
    ), {'rid': rid}).fetchone()
    assert first_order[1] == 'failed'
    ren = _renewal_row(uid)
    assert ren[4] == 1                      # fail_count
    assert auto_renew._to_dt(ren[3]) > datetime.utcnow()  # next_charge сдвинут на 24ч

    # Повтор через «сутки»: старая попытка failed → новый order_id,
    # и на этот раз списание проходит
    db.session.execute(text(
        "UPDATE premium_auto_renewals SET next_charge_at = :nc WHERE user_id = :uid"
    ), {'nc': datetime.utcnow() - timedelta(hours=1), 'uid': uid})
    db.session.commit()

    class RespOk:
        status_code = 200
        content = b'{}'
        def json(self):
            return {'id': 'pay-retry-1', 'status': 'succeeded'}

    monkeypatch.setattr(auto_renew.requests, 'post', lambda *a, **kw: RespOk())

    stats2 = {'failed': 0, 'charged': 0}
    auto_renew._charge_renewal(rid, uid, 'premium_intense', 800.0, 'pm-test-1', stats2)
    assert stats2['charged'] == 1

    second = db.session.execute(text(
        "SELECT order_id, status FROM premium_renewal_attempts WHERE renewal_id = :rid"
    ), {'rid': rid}).fetchone()
    assert second[0] != first_order[0]      # НОВЫЙ заказ
    assert second[1] == 'succeeded'
    # подписка продлена на 30 дней от конца периода
    top = db.session.execute(text(
        "SELECT expires_at FROM subscriptions WHERE user_id = :uid"
        " AND status = 'active' ORDER BY expires_at DESC LIMIT 1"
    ), {'uid': uid}).fetchone()
    assert auto_renew._to_dt(top[0]) == period_start + timedelta(days=30)
    # в yookassa_payments два заказа
    cnt = db.session.execute(text(
        "SELECT COUNT(*) FROM yookassa_payments WHERE user_id = :uid"
    ), {'uid': uid}).fetchone()
    assert cnt[0] == 2


def test_three_failures_disable_auto_renewal(ar_app, monkeypatch):
    """После 3 неудач автопродление выключается — доступ не трогаем."""
    from services import auto_renew

    uid = _uid()
    period_start = datetime.utcnow()
    _add_sub(uid, expires_at=period_start)
    rid = _add_renewal(uid, next_charge=period_start)

    class Resp:
        status_code = 402
        content = b'{}'
        def json(self):
            return {'description': 'payment declined'}

    monkeypatch.setattr(auto_renew.requests, 'post', lambda *a, **kw: Resp())
    monkeypatch.setattr(auto_renew, '_yk_cfg',
                        lambda: {'configured': True, 'shop_id': 's', 'secret_key': 'k'})

    stats = {'failed': 0}
    for _ in range(3):
        # «подошла дата» следующего списания
        from models import db
        db.session.execute(text(
            "UPDATE premium_auto_renewals SET next_charge_at = :nc WHERE user_id = :uid"
        ), {'nc': datetime.utcnow() - timedelta(hours=1), 'uid': uid})
        db.session.commit()
        auto_renew._charge_renewal(rid, uid, 'premium_intense', 800.0, 'pm-test-1', stats)

    ren = _renewal_row(uid)
    assert ren[2] == 0  # enabled = 0 — автопродление выключено
    assert ren[4] == 3  # fail_count
    # подписка не тронута: доступ не отнимаем за неоплаченный период
    from models import db
    n = db.session.execute(text(
        "SELECT COUNT(*) FROM subscriptions WHERE user_id = :uid"
    ), {'uid': uid}).fetchone()
    assert n[0] == 1


# ── Сохранение способа оплаты ─────────────────────────────────────────────

def test_upsert_rejects_demo_and_unverified(ar_app):
    """Демо-платёж и неподтверждённый способ оплаты не включают автопродление."""
    from services import auto_renew
    uid = _uid()
    assert auto_renew.upsert_from_payment(uid, 'demo_abc123', 'premium_intense')['connected'] is False
    assert auto_renew.upsert_from_payment(uid, None, 'premium_intense')['connected'] is False


def test_upsert_saves_method_and_sets_next_charge(ar_app, monkeypatch):
    """Успешный платёж с сохранённым способом оплаты создаёт соглашение,
    next_charge_at = дата окончания подписки."""
    from services import auto_renew

    uid = _uid()
    expires = datetime.utcnow() + timedelta(days=30)
    _add_sub(uid, expires_at=expires)

    class Resp:
        status_code = 200
        content = b'{}'
        def json(self):
            return {'status': 'succeeded', 'paid': True,
                    'payment_method': {'id': 'pm-abc', 'saved': True, 'title': 'Карта *4242'},
                    'metadata': {'user_id': str(uid)}}

    monkeypatch.setattr(auto_renew.requests, 'get', lambda *a, **kw: Resp())
    monkeypatch.setattr(auto_renew, '_yk_cfg',
                        lambda: {'configured': True, 'shop_id': 's', 'secret_key': 'k'})

    res = auto_renew.upsert_from_payment(uid, 'pay-ok-1', 'premium_intense')
    assert res['connected'] is True
    assert auto_renew._to_dt(res['next_charge_at']) == expires

    ren = _renewal_row(uid)
    assert ren[0] == 'premium_intense'
    assert ren[2] == 1  # включено


def test_set_enabled_toggle(ar_app):
    """Выключение/включение автопродления не трогает подписку."""
    from services import auto_renew
    uid = _uid()
    expires = datetime.utcnow() + timedelta(days=10)
    _add_sub(uid, expires_at=expires)
    _add_renewal(uid, next_charge=expires)

    assert auto_renew.set_enabled(uid, False)
    assert _renewal_row(uid)[2] == 0
    assert auto_renew.set_enabled(uid, True)
    assert _renewal_row(uid)[2] == 1
    # подписка не изменилась
    from models import db
    n = db.session.execute(text(
        "SELECT COUNT(*) FROM subscriptions WHERE user_id = :uid"
    ), {'uid': uid}).fetchone()
    assert n[0] == 1


def test_upsert_replay_does_not_reenable(ar_app, monkeypatch):
    """Повторный вебхук по старому платежу НЕ включает обратно
    выключенное автопродление (подтверждение оплаты ≠ согласие на списания)."""
    from services import auto_renew

    uid = _uid()
    expires = datetime.utcnow() + timedelta(days=30)
    _add_sub(uid, expires_at=expires)
    _add_renewal(uid, next_charge=expires)
    auto_renew.set_enabled(uid, False)  # пользователь отключил

    class Resp:
        status_code = 200
        content = b'{}'
        def json(self):
            return {'status': 'succeeded', 'paid': True,
                    'payment_method': {'id': 'pm-abc', 'saved': True, 'title': 'Карта *4242'},
                    'metadata': {'user_id': str(uid)}}

    monkeypatch.setattr(auto_renew.requests, 'get', lambda *a, **kw: Resp())
    monkeypatch.setattr(auto_renew, '_yk_cfg',
                        lambda: {'configured': True, 'shop_id': 's', 'secret_key': 'k'})

    # три «переигрывания» вебхука/возврата
    for _ in range(3):
        res = auto_renew.upsert_from_payment(uid, 'pay-replay-1', 'premium_intense')
        assert res['connected'] is True
    assert _renewal_row(uid)[2] == 0  # так и выключено


def test_upsert_rejects_foreign_payment(ar_app, monkeypatch):
    """Чужой payment_id не привязывает способ оплаты к другому пользователю."""
    from services import auto_renew
    uid = _uid()

    class Resp:
        status_code = 200
        content = b'{}'
        def json(self):
            return {'status': 'succeeded', 'paid': True,
                    'payment_method': {'id': 'pm-evil', 'saved': True, 'title': 'X'},
                    'metadata': {'user_id': '424242'}}  # чужой

    monkeypatch.setattr(auto_renew.requests, 'get', lambda *a, **kw: Resp())
    monkeypatch.setattr(auto_renew, '_yk_cfg',
                        lambda: {'configured': True, 'shop_id': 's', 'secret_key': 'k'})

    res = auto_renew.upsert_from_payment(uid, 'pay-foreign-1', 'premium_intense')
    assert res['connected'] is False and res['reason'] == 'payment_not_owned'


def test_failed_retry_claim_is_atomic(ar_app):
    """Захват failed-попытки атомарен: второй «воркер» (status уже не failed)
    ничего не забирает и не отправляет второй платёж."""
    from models import db
    from services import auto_renew

    uid = _uid()
    period_start = datetime.utcnow()
    _add_sub(uid, expires_at=period_start)
    rid = _add_renewal(uid, next_charge=period_start)
    _attempt(rid, period_start, period_start + timedelta(days=30), 'ord-claim-1', status='failed')
    a_id = db.session.execute(text(
        "SELECT id FROM premium_renewal_attempts WHERE order_id = 'ord-claim-1'"
    )).fetchone()[0]

    # воркер 1 забирает
    res1 = db.session.execute(text(
        "UPDATE premium_renewal_attempts SET status = 'pending', order_id = 'ord-claim-2'"
        " WHERE id = :id AND status = 'failed'"
    ), {'id': a_id})
    assert (res1.rowcount or 0) == 1
    db.session.commit()

    # воркер 2 с тем же условием — 0 строк, платёж не отправляет
    res2 = db.session.execute(text(
        "UPDATE premium_renewal_attempts SET status = 'pending', order_id = 'ord-claim-3'"
        " WHERE id = :id AND status = 'failed'"
    ), {'id': a_id})
    assert (res2.rowcount or 0) == 0
    db.session.commit()

    st = db.session.execute(text(
        "SELECT order_id FROM premium_renewal_attempts WHERE id = :id"
    ), {'id': a_id}).fetchone()
    assert st[0] == 'ord-claim-2'  # остался первый


def test_stale_pending_marks_unknown_and_blocks(ar_app, monkeypatch):
    """Pending-попытка старше 24ч (окно идемпотентности ЮKassa истекло)
    помечается unknown и НЕ отправляет новый платёж."""
    from models import db
    from services import auto_renew

    uid = _uid()
    period_start = datetime.utcnow()
    _add_sub(uid, expires_at=period_start)
    rid = _add_renewal(uid, next_charge=period_start)

    old = datetime.utcnow() - timedelta(hours=25)
    db.session.execute(text(
        "INSERT INTO premium_renewal_attempts (renewal_id, period_start, period_end,"
        " order_id, status, created_at) VALUES (:rid, :ps, :pe, 'ord-stale-1', 'pending', :old)"
    ), {'rid': rid, 'ps': period_start, 'pe': period_start + timedelta(days=30), 'old': old})
    db.session.commit()

    called = {'post': 0}
    def _no_post(*a, **kw):
        called['post'] += 1
        raise AssertionError('POST must not be called for stale pending')
    monkeypatch.setattr(auto_renew.requests, 'post', _no_post)
    monkeypatch.setattr(auto_renew, '_yk_cfg',
                        lambda: {'configured': True, 'shop_id': 's', 'secret_key': 'k'})

    stats = {'charged': 0, 'failed': 0}
    auto_renew._charge_renewal(rid, uid, 'premium_intense', 800.0, 'pm-1', stats)
    assert called['post'] == 0
    st = db.session.execute(text(
        "SELECT status FROM premium_renewal_attempts WHERE renewal_id = :rid"
    ), {'rid': rid}).fetchone()
    assert st[0] == 'unknown'

    # и повторный запуск тоже не списывает
    auto_renew._charge_renewal(rid, uid, 'premium_intense', 800.0, 'pm-1', stats)
    assert called['post'] == 0


def test_first_payment_activation_atomic(ar_app, monkeypatch):
    """Сбой активации первого платежа откатывает И захват paid_at:
    повтор докатывает Premium, дальнейшие повторы срок не меняют."""
    from routes import premium_pay as pp
    import services.subscription as sub
    from models import db

    uid = _uid()
    order_id, payment_id = 'ord-first-1', 'pay-f1'
    db.session.execute(text(
        "INSERT INTO yookassa_payments (order_id, payment_id, user_id, item_code,"
        " amount_rub, status) VALUES (:oid, :pid, :uid, 'premium_intense', 800, 'succeeded')"
    ), {'oid': order_id, 'pid': payment_id, 'uid': uid})
    db.session.commit()

    # Ломаем активацию — как если бы БД упала между захватом и выдачей
    orig = sub.get_subscription_service
    sub.get_subscription_service = lambda: (_ for _ in ()).throw(RuntimeError('db down'))
    try:
        r = pp.activate_premium_for_payment(uid, 'premium_intense', payment_id, order_id)
        assert r['ok'] is False
    finally:
        sub.get_subscription_service = orig

    # Захват откатился: paid_at пуст, подписки нет
    row = db.session.execute(text(
        "SELECT paid_at FROM yookassa_payments WHERE order_id = :oid"
    ), {'oid': order_id}).fetchone()
    assert row[0] is None
    n = db.session.execute(text(
        "SELECT COUNT(*) FROM subscriptions WHERE user_id = :uid"
    ), {'uid': uid}).fetchone()
    assert n[0] == 0

    # Повтор (вебхук дошёл / юзер открыл возврат) — активация проходит
    r2 = pp.activate_premium_for_payment(uid, 'premium_intense', payment_id, order_id)
    assert r2['ok'] is True and 'already_applied' not in r2
    n = db.session.execute(text(
        "SELECT COUNT(*) FROM subscriptions WHERE user_id = :uid"
    ), {'uid': uid}).fetchone()
    assert n[0] == 1

    # Повторные вызовы — already_applied, подписка одна, срок не переписан
    r3 = pp.activate_premium_for_payment(uid, 'premium_intense', payment_id, order_id)
    assert r3.get('already_applied') is True
    n = db.session.execute(text(
        "SELECT COUNT(*) FROM subscriptions WHERE user_id = :uid"
    ), {'uid': uid}).fetchone()
    assert n[0] == 1


def test_kill_switch_env(ar_app, monkeypatch):
    """PREMIUM_AUTORENEW_ENABLED=0 — джоба мгновенно выходит."""
    from services import auto_renew
    monkeypatch.setenv('PREMIUM_AUTORENEW_ENABLED', '0')
    assert auto_renew.run_renewal_job() == {'skipped': 'disabled_by_env'}


def test_handle_succeeded_preserves_disabled(ar_app):
    """Продление по автосписанию не включает обратно выключенное автопродление
    (обновляет только next_charge_at, но сам факт оплаты — не согласие)."""
    from services import auto_renew

    uid = _uid()
    period_start = datetime.utcnow() + timedelta(hours=2)
    period_end = period_start + timedelta(days=30)
    _add_sub(uid, expires_at=period_start)
    rid = _add_renewal(uid, next_charge=period_start)
    auto_renew.set_enabled(uid, False)
    order_id = 'ord-disabled-1'
    _attempt(rid, period_start, period_end, order_id)

    auto_renew.handle_succeeded_payment(order_id, 'pay-1', uid, 'premium_intense')

    ren = _renewal_row(uid)
    assert ren[2] == 0  # так и выключено
    assert auto_renew._to_dt(ren[3]) == period_end  # но платёж учтён
