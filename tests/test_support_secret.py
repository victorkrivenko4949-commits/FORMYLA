# -*- coding: utf-8 -*-
"""SECURITY: секрет входа поддержки (Lavrik) из БД, задаётся через /admin.

Полный цикл: админ задаёт секрет → вход по секрету в Lavrik работает
(в любом регистре) → удаление секрета → вход отключён.

Запуск: pytest tests/test_support_secret.py -q
"""
import pytest

from app import app as real_app, _get_support_login_secret  # noqa: E402


def _make_onboarded(user_id, email, nickname):
    """Юзер + CuratorState с пройденной анкетой (иначе intake-гейт редиректит)."""
    from models import db, User
    from models_curator import CuratorState
    from datetime import datetime as _dtn
    with real_app.app_context():
        u = User.query.get(user_id)
        if not u:
            u = User(email=email, nickname=nickname, onboarded_at=_dtn.utcnow())
            u.id = user_id
            db.session.add(u)
        else:
            u.onboarded_at = u.onboarded_at or _dtn.utcnow()
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if not cs:
            cs = CuratorState(user_id=user_id)
            db.session.add(cs)
        cs.prep_state = {"intake": {"completed": True, "skipped": False}}
        db.session.commit()


@pytest.fixture
def client(monkeypatch):
    real_app.config['TESTING'] = True
    # env-секрет не задан — тестируем путь через БД
    import app as app_module
    monkeypatch.setattr(app_module, 'SUPPORT_LOGIN_SECRET_ENV', '')

    from models import db, User
    with real_app.app_context():
        db.create_all()
        db.session.rollback()  # сброс незакоммиченных добавок прошлого теста
        db.session.execute(db.text(
            "CREATE TABLE IF NOT EXISTS app_config ("
            "config_key VARCHAR(64) PRIMARY KEY, config_value TEXT, "
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
        db.session.execute(db.text(
            "DELETE FROM app_config WHERE config_key = 'support_login_secret'"))
        User.query.filter(User.nickname.in_(
            ['Lavrik', 'admin_t', 'plain_t'])).delete(synchronize_session=False)
        db.session.commit()

    c = real_app.test_client()
    yield c

    with real_app.app_context():
        from models import User as U
        db.session.execute(db.text(
            "CREATE TABLE IF NOT EXISTS app_config ("
            "config_key VARCHAR(64) PRIMARY KEY, config_value TEXT, "
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
        db.session.execute(db.text(
            "DELETE FROM app_config WHERE config_key = 'support_login_secret'"))
        U.query.filter_by(nickname='Lavrik').delete()
        db.session.commit()


def _login_as(c, user_id):
    with c.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


def test_secret_cycle(client):
    c = client

    # 1. Секрета нет → обычный путь: редирект на /verify-code, не в кабинет
    assert _get_support_login_secret() == ''
    r = c.post('/login', data={'email': 'random-user-xyz@example.com'},
               follow_redirects=False)
    assert r.status_code == 302 and '/verify-code' in r.headers.get('Location', '')

    # 2. Админ задаёт секрет
    _make_onboarded(1, 'admin@example.com', 'admin_t')
    _login_as(c, 1)
    r = c.post('/admin/support_secret',
               data={'secret': 'formyla-support-test-secret-12345'})
    assert r.status_code == 200
    assert r.get_json()['status'] == 'ok'

    # 3. Секрет разрешается из БД
    with real_app.app_context():
        assert _get_support_login_secret() == 'formyla-support-test-secret-12345'

    # 4. Вход по секрету работает (в верхнем регистре тоже — email.lower)
    c.get('/logout')
    r = c.post('/login', data={'email': 'FORMYLA-SUPPORT-TEST-SECRET-12345'},
               follow_redirects=False)
    assert r.status_code == 302 and '/profile' in r.headers.get('Location', '')
    from models import User
    with real_app.app_context():
        lavrik = User.query.filter_by(nickname='Lavrik').first()
        assert lavrik is not None  # служебный аккаунт создан

    # 5. Удаление секрета → вход снова отключён
    _login_as(c, 1)
    r = c.post('/admin/support_secret', data={'action': 'clear'})
    assert r.get_json()['status'] == 'ok'
    with real_app.app_context():
        assert _get_support_login_secret() == ''


def test_short_secret_rejected(client):
    """Короткий секрет отклоняется (минимум 16 символов)."""
    c = client
    _make_onboarded(1, 'admin@example.com', 'admin_t')
    _login_as(c, 1)
    r = c.post('/admin/support_secret', data={'secret': 'short'})
    assert r.status_code == 400


def test_non_admin_forbidden(client):
    """Не-админ не может задать секрет."""
    c = client
    _make_onboarded(999, 'plain@example.com', 'plain_t')
    _login_as(c, 999)
    r = c.post('/admin/support_secret', data={'secret': 'x' * 30})
    assert r.status_code == 403
