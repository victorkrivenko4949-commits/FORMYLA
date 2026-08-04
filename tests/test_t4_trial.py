# -*- coding: utf-8 -*-
"""tests/test_t4_trial.py — T4 trial access tests.

Tests on fixtures: user_trial_active, user_trial_expired, user_subscribed.
Verifies has_access() guard behaviour.
Does NOT write to instance/formyla.db.
"""

import pytest


# ── Model-level access logic tests ─────────────────────────────────────

@pytest.mark.parametrize('user_fixture,expected', [
    ('user_trial_active', True),
    ('user_trial_expired', False),
    ('user_subscribed', True),
])
def test_has_access_logic(request, user_fixture, expected):
    """has_access() returns correct boolean for each user type."""
    user = request.getfixturevalue(user_fixture)
    assert user.has_access() == expected, (
        f'{user_fixture}: has_access() = {user.has_access()}, '
        f'expected {expected}'
    )


@pytest.mark.parametrize('user_fixture,trial_expected,sub_expected', [
    ('user_trial_active', True, False),
    ('user_trial_expired', False, False),
    ('user_subscribed', False, True),
])
def test_trial_and_sub_methods(request, user_fixture,
                               trial_expected, sub_expected):
    """is_trial_active and has_active_subscription work independently."""
    user = request.getfixturevalue(user_fixture)
    assert user.is_trial_active() == trial_expected, (
        f'{user_fixture}: is_trial_active()={user.is_trial_active()} '
        f'(expected {trial_expected})'
    )
    assert user.has_active_subscription() == sub_expected, (
        f'{user_fixture}: has_active_subscription()='
        f'{user.has_active_subscription()} (expected {sub_expected})'
    )


# ── HTTP-level guard tests ─────────────────────────────────────────────


def test_trial_expired_blocked_on_probe(client, app, user_trial_expired):
    """Expired trial + no sub: /prep/probe returns 402 with trial-expired text."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_trial_expired.id)

    r = client.get('/prep/probe', follow_redirects=False)
    assert r.status_code != 500, (
        f'/prep/probe returned 500 (internal error)'
    )
    body = r.data.decode('utf-8') if r.data else ''
    assert 'Триальный период окончен' in body, (
        f'/prep/probe blocked but missing "Триальный период окончен". '
        f'Body[:300]: {body[:300]}'
    )


def test_trial_active_passes_guard(client, app, user_trial_active):
    """Active trial: /prep/probe does NOT return 402."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_trial_active.id)

    r = client.get('/prep/probe', follow_redirects=False)
    assert r.status_code != 402, (
        f'/prep/probe returned {r.status_code} (402=blocked), '
        f'expected access granted'
    )


def test_subscribed_passes_guard(client, app, user_subscribed):
    """Active subscription: /prep/probe does NOT return 402."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_subscribed.id)

    r = client.get('/prep/probe', follow_redirects=False)
    assert r.status_code != 402, (
        f'/prep/probe returned {r.status_code} (402=blocked), '
        f'expected access granted'
    )


def test_basic_routes_open(client, app, user_trial_expired):
    """Root is always accessible even for expired-trial users."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_trial_expired.id)

    r = client.get('/', follow_redirects=True)
    assert r.status_code not in (402, 500), (
        f'/ returned {r.status_code}, expected non-402 non-500'
    )
