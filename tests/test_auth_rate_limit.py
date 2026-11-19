# -*- coding: utf-8 -*-
"""SECURITY: рейт-лимиты auth-эндпоинтов.

1. per-email cooldown 60с на отправку письма с кодом (анти-спам ящика жертвы)
2. per-IP лимит POST /login (8/10мин)
3. per-IP лимит POST /verify-code (40/10мин)

Запуск: pytest tests/test_auth_rate_limit.py -q
"""
import pytest

import app as app_module
from app import app as real_app  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    real_app.config['TESTING'] = True
    # Mail «настроен», чтобы шла ветка отправки письма
    monkeypatch.setattr(real_app, 'config', {**real_app.config, 'MAIL_USERNAME': 't', 'MAIL_PASSWORD': 't'})
    from utils import mail as _mail
    monkeypatch.setattr(_mail, 'is_configured', lambda: True)

    sent = []
    monkeypatch.setattr(app_module, 'send_auth_email', lambda email, code: sent.append((email, code)))

    # чистый рейт-лимитер на время теста
    monkeypatch.setattr(app_module, '_AUTH_RATE', app_module._dd(lambda: app_module._dd(app_module._dq)))

    from models import db, User
    with real_app.app_context():
        db.create_all()
        User.query.filter_by(email='ratelimit@example.com').delete()
        db.session.commit()
        u = User(email='ratelimit@example.com', nickname='ratelimit_t')
        u.generate_auth_code()
        db.session.add(u)
        db.session.commit()

    c = real_app.test_client()
    yield c, sent

    with real_app.app_context():
        User.query.filter_by(email='ratelimit@example.com').delete()
        db.session.commit()


def test_email_cooldown_no_resend_within_60s(client):
    """Повторный /login в течение минуты НЕ шлёт второе письмо (тот же код)."""
    c, sent = client
    c.post('/login', data={'email': 'ratelimit@example.com'})
    assert len(sent) == 1
    c.post('/login', data={'email': 'ratelimit@example.com'})
    assert len(sent) == 1  # cooldown — письмо не продублировалось


def test_login_ip_rate_limit(client):
    """Больше 8 POST /login с одного IP за окно — 429."""
    c, sent = client
    statuses = []
    for _ in range(10):
        r = c.post('/login', data={'email': 'ratelimit@example.com'})
        statuses.append(r.status_code)
    assert statuses.count(429) >= 2  # 9-й и 10-й запрос отклонены
    assert statuses.count(429) + statuses.count(302) == 10  # остальные — редирект (норм. поток)


def test_verify_code_ip_rate_limit(client):
    """Больше 40 POST /verify-code с одного IP за окно — 429."""
    c, sent = client
    statuses = []
    with c.session_transaction() as sess:
        sess['verify_email'] = 'ratelimit@example.com'
    for _ in range(45):
        r = c.post('/verify-code', data={'code': '000000'})
        statuses.append(r.status_code)
    assert statuses.count(429) >= 5  # 41-й и далее отклонены
