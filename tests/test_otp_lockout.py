# -*- coding: utf-8 -*-
"""SECURITY: серверный лимит неверных попыток OTP (per-email, в БД).

Раньше счётчик попыток жил в session cookie — сброс куки давал новые
5 попыток против того же кода (перебор 6-значного кода без ограничений).
Тест проверяет: после 5 неверных попыток вход блокируется ДАЖЕ в новой
сессии, и сбрасывается только генерацией нового кода.

Запуск: pytest tests/test_otp_lockout.py -q
"""
import pytest

from app import app as real_app  # noqa: E402


@pytest.fixture
def client():
    real_app.config['TESTING'] = True
    from models import db, User
    with real_app.app_context():
        db.create_all()
        User.query.filter_by(email='locktest@example.com').delete()
        db.session.commit()
        u = User(email='locktest@example.com', nickname='locktest_otp')
        u.generate_auth_code()
        db.session.add(u)
        db.session.commit()
        email, code = 'locktest@example.com', u.auth_code
    c = real_app.test_client()
    yield c, email
    with real_app.app_context():
        User.query.filter_by(email='locktest@example.com').delete()
        db.session.commit()


def _post_code(client, email, code):
    with client.session_transaction() as sess:
        sess['verify_email'] = email
    return client.post('/verify-code', data={'code': code}, follow_redirects=True)


def test_locked_across_sessions(client):
    """5 неверных попыток → блокировка действует и в новой сессии."""
    c, email = client

    # Сессия 1: пять неверных кодов — каждая попытка принимается к проверке
    for i in range(5):
        resp = _post_code(c, email, f'00000{i}')
        assert resp.status_code == 200

    from models import User
    with real_app.app_context():
        u = User.query.filter_by(email=email).first()
        assert u.failed_code_attempts == 5
        real_code = u.auth_code

    # Сессия 2 (мошенник сбросил куки): даже ВЕРНЫЙ код отклоняется
    c2 = real_app.test_client()
    resp = _post_code(c2, email, real_code)
    body = resp.get_data(as_text=True)
    assert 'Слишком много неверных попыток' in body
    with c2:
        c2.get('/login')
        from flask_login import current_user
        assert not current_user.is_authenticated

    # Счётчик не растёт дальше (серверный лимит, а не сессионный)
    with real_app.app_context():
        u = User.query.filter_by(email=email).first()
        assert u.failed_code_attempts == 5


def test_new_code_resets_counter(client):
    """Запрос нового кода сбрасывает счётчик — легитимный пользователь не страдает."""
    c, email = client
    from models import User

    for i in range(5):
        _post_code(c, email, f'00000{i}')

    with real_app.app_context():
        u = User.query.filter_by(email=email).first()
        assert u.failed_code_attempts == 5

    # Запрос нового кода через /login
    c.post('/login', data={'email': email}, follow_redirects=True)

    with real_app.app_context():
        u = User.query.filter_by(email=email).first()
        assert u.failed_code_attempts == 0
        new_code = u.auth_code

    # Теперь верный код работает
    resp = _post_code(c, email, new_code)
    assert resp.status_code == 200
    with c:
        c.get('/login')
        from flask_login import current_user
        assert current_user.is_authenticated
