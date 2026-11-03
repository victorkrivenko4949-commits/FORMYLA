# -*- coding: utf-8 -*-
"""PARENT_PREMIUM_500 — регрессия ошибки 500 в кабинете родителя.

Причина: PostgreSQL возвращает subscriptions.expires_at как datetime,
а шаблон кабинета резал его срезом [:10] (TypeError) — страница /parent
падала с 500 у любого родителя, у ребёнка которого активен Premium.

Запуск: pytest tests/test_parent_premium_date.py -q
"""
from datetime import datetime

import pytest

from models import db, User, ParentChildLink


@pytest.fixture
def parent_with_child(app, student_users):
    """Родитель + подтверждённая связь с учеником (как требует CONFIRM_LINK_V1)."""
    parent = User(
        email='parent_premium@example.invalid',
        nickname='parent_premium',
        role='parent',
        is_guest=False,
    )
    db.session.add(parent)
    db.session.flush()
    link = ParentChildLink(
        parent_id=parent.id,
        child_id=student_users[0].id,
        status='accepted',
        responded_at=datetime.utcnow(),
    )
    db.session.add(link)
    db.session.commit()
    return parent, student_users[0]


def _stub_subscription_service(expires_at):
    """Заглушка сервиса подписок: get_user_plan возвращает заданный expires_at."""
    class _StubService:
        def get_user_plan(self, user_id):
            return {
                'plan': 'premium_monthly',
                'is_premium': expires_at is not None,
                'expires_at': expires_at,
            }

    return _StubService()


class TestParentDashboardPremiumDate:
    """GET /parent — дата Premium не роняет страницу."""

    def test_datetime_expires_at_from_postgres(self, app, parent_with_child, monkeypatch):
        """PostgreSQL: expires_at — datetime. До фикса — 500, после — 200."""
        parent, _child = parent_with_child
        import services.subscription as sub_mod
        monkeypatch.setattr(
            sub_mod, 'get_subscription_service',
            lambda: _stub_subscription_service(datetime(2026, 12, 31, 23, 59, 0)),
        )

        with app.test_client() as c:
            with c.session_transaction() as s:
                s['_user_id'] = str(parent.id)
            r = c.get('/parent', follow_redirects=False)
            assert r.status_code == 200, f'Expected 200, got {r.status_code}'
            text = r.data.decode('utf-8')
            assert '2026-12-31' in text, 'Premium expiry date not rendered'

    def test_string_expires_at_from_sqlite(self, app, parent_with_child, monkeypatch):
        """SQLite: expires_at — ISO-строка. Страница работает и дата видна."""
        parent, _child = parent_with_child
        import services.subscription as sub_mod
        monkeypatch.setattr(
            sub_mod, 'get_subscription_service',
            lambda: _stub_subscription_service('2026-12-31T23:59:00'),
        )

        with app.test_client() as c:
            with c.session_transaction() as s:
                s['_user_id'] = str(parent.id)
            r = c.get('/parent', follow_redirects=False)
            assert r.status_code == 200, f'Expected 200, got {r.status_code}'
            text = r.data.decode('utf-8')
            assert '2026-12-31' in text, 'Premium expiry date not rendered'

    def test_no_premium(self, app, parent_with_child, monkeypatch):
        """Без Premium кнопка покупки рисуется, страница живая."""
        parent, _child = parent_with_child
        import services.subscription as sub_mod
        monkeypatch.setattr(
            sub_mod, 'get_subscription_service',
            lambda: _stub_subscription_service(None),
        )

        with app.test_client() as c:
            with c.session_transaction() as s:
                s['_user_id'] = str(parent.id)
            r = c.get('/parent', follow_redirects=False)
            assert r.status_code == 200, f'Expected 200, got {r.status_code}'
            text = r.data.decode('utf-8')
            assert 'Купить Premium' in text, 'Buy Premium button not rendered'
