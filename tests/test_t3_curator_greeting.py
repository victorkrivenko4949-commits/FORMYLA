# -*- coding: utf-8 -*-
"""tests/test_t3_curator_greeting.py — T3: curator greets by name.

Tests cover:
  1. display_name_from_email returns "Виктор" for victorkrvnk@gmail.com.
  2. display_name_from_email transliterates unknown names correctly.
  3. coach_greeting JSON contains personalized name for logged-in user.
  4. Coach greeting JSON returns "Привет!" without name for user
     with no email (no crash).
  5. Fallback edge cases: empty email, no @ sign, digit-only.
"""

import pytest
from models import db, User


@pytest.fixture
def victor_user(app):
    """Create a test user with victorkrvnk@gmail.com email and grade."""
    user = User(
        email='victorkrvnk@gmail.com',
        nickname='victor_test',
        is_guest=False,
        preferred_grade=7,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def victor_client(client, victor_user):
    """Authorised test client with victor_user session."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(victor_user.id)
    return client


@pytest.fixture
def alien_user(app):
    """Create a test user with unknown transliterated email."""
    user = User(
        email='oleg123@example.com',
        nickname='oleg_test',
        is_guest=False,
        preferred_grade=8,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def alien_client(client, alien_user):
    """Authorised test client with alien_user session."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(alien_user.id)
    return client


@pytest.fixture
def noemail_user(app):
    """Create a test user without email."""
    user = User(
        email='noemail@example.invalid',
        nickname='noemail_test',
        is_guest=False,
        preferred_grade=7,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def noemail_client(client, noemail_user):
    """Authorised test client with noemail_user session."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(noemail_user.id)
    return client


# ── Unit tests for display_name_from_email ──

def test_display_name_victor():
    """display_name_from_email returns 'Виктор' for victorkrvnk@gmail.com."""
    from services.user_helpers import display_name_from_email
    name = display_name_from_email('victorkrvnk@gmail.com')
    assert name == 'Виктор', f"Expected 'Виктор', got '{name}'"


def test_display_name_unknown():
    """display_name_from_email transliterates unknown names."""
    from services.user_helpers import display_name_from_email
    name = display_name_from_email('oleg123@example.com')
    assert name == 'Олег', f"Expected 'Олег', got '{name}'"


def test_display_name_fallback():
    """display_name_from_email handles edge cases."""
    from services.user_helpers import display_name_from_email
    assert display_name_from_email('') == 'Игрок'
    assert display_name_from_email(None) == 'Игрок'
    assert display_name_from_email('no_at_sign') == 'Игрок'
    name = display_name_from_email('123456@x.com')
    assert name.startswith('Игрок'), f"Should start with 'Игрок', got '{name}'"


# ── Integration tests: coach_greeting endpoint ──

def test_coach_greeting_contains_victor(victor_client):
    """GET /prep/coach/greeting returns JSON with 'Привет, Виктор!'."""
    r = victor_client.get('/prep/coach/greeting')
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.get_json()
    assert data is not None, "Response should be JSON"
    greeting = data.get('greeting', '')
    assert 'Привет, Виктор!' in greeting, (
        f"Greeting should contain 'Привет, Виктор!', got: {greeting[:200]}"
    )


def test_coach_greeting_contains_oleg(alien_client):
    """GET /prep/coach/greeting returns JSON with 'Привет, Олег!'."""
    r = alien_client.get('/prep/coach/greeting')
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.get_json()
    assert data is not None, "Response should be JSON"
    greeting = data.get('greeting', '')
    assert 'Привет, Олег!' in greeting, (
        f"Greeting should contain 'Привет, Олег!', got: {greeting[:200]}"
    )


def test_coach_greeting_has_personal_prefix(victor_client):
    """Coach greeting JSON should NOT be a bare static 'Привет!'."""
    r = victor_client.get('/prep/coach/greeting')
    assert r.status_code == 200
    data = r.get_json()
    greeting = data.get('greeting', '')
    # With victor user, greeting should start with "Привет, Виктор!"
    # not just bare "Привет!"
    assert greeting.startswith('Привет, Виктор!'), (
        f"Greeting should start with 'Привет, Виктор!', got: {greeting[:100]}"
    )
