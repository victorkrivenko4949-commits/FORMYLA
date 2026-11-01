# -*- coding: utf-8 -*-
"""PILOT_EMAIL_V1 (01.11.2026): пилотский доступ по email — покупка тарифов
для аккаунта viktorformulevitch@yandex.ru до общего старта 3 ноября.

Email-пилот: is_pilot_user проверяет PILOT_EMAILS (по объекту User — без
запроса в БД, по int id — через users.email). Для email из
PILOT_REVOKE_BETA_EMAILS бесплатная бета не выдаётся (проверка оплаты).

Запуск: pytest tests/test_pilot_email.py -q
"""
import pytest

import services.pilot as pilot_mod
from services.pilot import (
    ensure_pilot_subscriptions,
    is_pilot_user,
)

_SPACER = {'done': False}


def _make_user(email, nickname):
    """Пользователь с id, не совпадающим с PILOT_USER_IDS (1, 5, 7452):
    в чистой базе первый insert получает id=1 (пилот victor) — нужен spacer."""
    from models import db, User
    if User.query.count() == 0:
        db.session.add(User(email='spacer@example.invalid',
                            nickname='spacer', is_guest=False))
        db.session.commit()
    u = User(email=email, nickname=nickname, is_guest=False)
    db.session.add(u)
    db.session.commit()
    assert u.id not in pilot_mod.PILOT_USER_IDS
    return u


@pytest.fixture
def email_pilots_only(monkeypatch):
    """Убираем id-пилотов: тестируем только email-механику."""
    monkeypatch.setattr(pilot_mod, 'PILOT_USER_IDS', ())
    monkeypatch.setattr(pilot_mod, 'PILOT_REVOKE_BETA_IDS', ())


# ── is_pilot_user: объект User ──────────────────────────────────────────────

def test_pilot_user_by_email_object(app):
    u = _make_user('viktorformulevitch@yandex.ru', 'viktorf')
    assert is_pilot_user(u) is True


def test_pilot_email_case_insensitive(app):
    u = _make_user('VIKTORFORMULEVITCH@yandex.ru ', 'viktorf2')
    assert is_pilot_user(u) is True


def test_non_pilot_user_still_false(app):
    u = _make_user('random@example.invalid', 'randomer')
    assert is_pilot_user(u) is False


# ── is_pilot_user: int id (маршруты оплаты передают current_user.id) ────────

def test_pilot_user_by_id_db_lookup(app):
    u = _make_user('viktorformulevitch@yandex.ru', 'viktorf3')
    assert is_pilot_user(u.id) is True


def test_non_pilot_id_still_false(app):
    u = _make_user('random2@example.invalid', 'randomer2')
    assert is_pilot_user(u.id) is False


def test_hardcoded_pilot_ids_untouched(app):
    assert is_pilot_user(5) is True    # Lavrik
    assert is_pilot_user(7452) is True  # Damian


# ── ensure_pilot_subscriptions: email-пилот без бесплатной беты ─────────────

def test_revoke_email_gets_no_free_beta(app, email_pilots_only):
    """viktorformulevitch — email из PILOT_REVOKE_BETA_EMAILS: бета не выдаётся,
    активная бета снимается. Доступ к Premium — только после оплаты."""
    from models import db
    from services.subscription import get_subscription_service
    u = _make_user('viktorformulevitch@yandex.ru', 'viktorf4')
    svc = get_subscription_service()
    svc.activate_premium(user_id=u.id, plan='premium_intense', is_beta=True)
    db.session.commit()
    assert svc.get_user_plan(u.id).get('is_premium') is True

    ok = ensure_pilot_subscriptions()
    db.session.commit()
    assert ok is True
    assert svc.get_user_plan(u.id).get('is_premium') is not True


def test_pilot_email_without_revoke_gets_beta(app, email_pilots_only, monkeypatch):
    """email-пилот вне revoke-списка получает бету, как id-пилоты."""
    from models import db
    from services.subscription import get_subscription_service
    u = _make_user('betaemail@example.invalid', 'beta_emailer')
    svc = get_subscription_service()
    assert svc.get_user_plan(u.id).get('is_premium') is not True

    monkeypatch.setattr(pilot_mod, 'PILOT_EMAILS', ('betaemail@example.invalid',))
    monkeypatch.setattr(pilot_mod, 'PILOT_REVOKE_BETA_EMAILS', ())
    ok = ensure_pilot_subscriptions()
    db.session.commit()
    assert ok is True
    assert svc.get_user_plan(u.id).get('is_premium') is True


def test_missing_email_account_does_not_break_startup(app, email_pilots_only, monkeypatch):
    """Аккаунта с pilot-email нет в БД — старт приложения не падает."""
    monkeypatch.setattr(pilot_mod, 'PILOT_EMAILS', ('ghost@example.invalid',))
    monkeypatch.setattr(pilot_mod, 'PILOT_REVOKE_BETA_EMAILS', ('ghost@example.invalid',))
    assert ensure_pilot_subscriptions() is False  # изменений нет
