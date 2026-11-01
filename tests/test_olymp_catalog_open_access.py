# -*- coding: utf-8 -*-
"""Каталог олимпиад открыт всем авторизованным (OLYMP_CATALOG_USERS="*").

Регрессия к смене белого списка OLYMP_CATALOG_USERS (lavrik,victor) на открытый
доступ: обычный пользователь видит каталог, аноним перенаправляется на логин,
а явный белый список по-прежнему работает (обратимость через env).

ИИ-тьютор каталога при этом остаётся за paywall Premium — см.
test_free_tier_gating.py::test_olymp_tutor_api_gated.

Запуск: pytest tests/test_olymp_catalog_open_access.py -q
"""
import pytest


def _mk_user(appl, email):
    from models import db, User
    u = User(email=email, is_guest=False)
    db.session.add(u)
    db.session.commit()
    return u


def _client(appl, user):
    c = appl.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id)
    return c


@pytest.fixture
def catalog_app(app):
    """Тестовое приложение + blueprint каталога (conftest его не регистрирует)."""
    from routes.olymp_catalog import olymp_catalog_bp
    if 'olymp_catalog' not in app.blueprints:
        app.register_blueprint(olymp_catalog_bp)
    return app


def test_catalog_open_for_regular_user(catalog_app, monkeypatch):
    """Дефолт: обычный (не из старого белого списка) пользователь видит каталог."""
    monkeypatch.delenv('OLYMP_CATALOG_USERS', raising=False)
    u = _mk_user(catalog_app, 'catalog_open@x.invalid')
    c = _client(catalog_app, u)
    r = c.get('/olymp-catalog/')
    assert r.status_code == 200
    assert r.status_code != 403


def test_catalog_anonymous_redirected_to_login(catalog_app):
    """Аноним остаётся за логином (каталог открыт всем авторизованным, не публично)."""
    c = catalog_app.test_client()
    r = c.get('/olymp-catalog/')
    assert r.status_code == 302
    assert '/login' in r.headers.get('Location', '')


def test_catalog_whitelist_still_supported(catalog_app, monkeypatch):
    """OLYMP_CATALOG_USERS="lavrik,victor" возвращает старое поведение белого списка."""
    monkeypatch.setenv('OLYMP_CATALOG_USERS', 'lavrik,victor')
    u = _mk_user(catalog_app, 'catalog_denied@x.invalid')
    c = _client(catalog_app, u)
    r = c.get('/olymp-catalog/')
    assert r.status_code == 403
