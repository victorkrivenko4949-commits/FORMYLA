# -*- coding: utf-8 -*-
"""REPRO: 500 при открытии группы учителя, если у ученика активен Premium.

PostgreSQL возвращает subscriptions.expires_at как datetime, а шаблон
templates/teacher/group.html режет его срезом [:10] — TypeError → 500.
"""
from datetime import datetime

import pytest


class _StubService:
    def __init__(self, expires_at):
        self._expires_at = expires_at

    def get_user_plan(self, user_id):
        return {
            'plan': 'premium_monthly',
            'is_premium': self._expires_at is not None,
            'expires_at': self._expires_at,
        }


def _login(client, user):
    with client.session_transaction() as s:
        s['_user_id'] = str(user.id)


def test_teacher_group_page_datetime_premium(app, teacher_user, student_users,
                                            group_with_students, monkeypatch):
    import services.subscription as sub_mod
    monkeypatch.setattr(
        sub_mod, 'get_subscription_service',
        lambda: _StubService(datetime(2026, 12, 31, 23, 59, 0)),
    )

    with app.test_client() as c:
        _login(c, teacher_user)
        r = c.get(f'/teacher/group/{group_with_students.id}')
        assert r.status_code == 200, (
            f'Expected 200, got {r.status_code}\n{r.data.decode("utf-8", "replace")[:2000]}'
        )
        text = r.data.decode('utf-8')
        assert '2026-12-31' in text, 'Premium expiry date not rendered'
