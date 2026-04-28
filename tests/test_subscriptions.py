# -*- coding: utf-8 -*-
"""
Unit tests for the Free/Premium subscription system.

Run:
    pytest tests/test_subscriptions.py -v

Uses in-memory SQLite via conftest.py fixtures — no formyla.db touched.
"""

import pytest
from datetime import datetime, timedelta

from services.subscription import PLAN_LIMITS


# ── PLAN_LIMITS constants ─────────────────────────────────────────────────────

class TestPlanLimits:
    def test_free_plan_exists(self):
        assert 'free' in PLAN_LIMITS

    def test_premium_monthly_exists(self):
        assert 'premium_monthly' in PLAN_LIMITS

    def test_premium_yearly_exists(self):
        assert 'premium_yearly' in PLAN_LIMITS

    def test_free_tasks_limit(self):
        assert PLAN_LIMITS['free']['tasks_per_day'] == 20

    def test_free_ai_limit(self):
        assert PLAN_LIMITS['free']['ai_explanations_per_day'] == 3

    def test_free_max_tokens(self):
        assert PLAN_LIMITS['free']['ai_max_tokens'] == 2000

    def test_premium_max_tokens(self):
        assert PLAN_LIMITS['premium_monthly']['ai_max_tokens'] == 8000

    def test_premium_tasks_unlimited(self):
        assert PLAN_LIMITS['premium_monthly']['tasks_per_day'] is None

    def test_premium_ai_unlimited_daily(self):
        assert PLAN_LIMITS['premium_monthly']['ai_explanations_per_day'] is None

    def test_premium_price(self):
        assert PLAN_LIMITS['premium_monthly']['price_rub'] == 390

    def test_yearly_price(self):
        assert PLAN_LIMITS['premium_yearly']['price_rub'] == 3900


# ── Test 1: New user is free ──────────────────────────────────────────────────

def test_new_user_is_free(service, test_user):
    """Test 1: регистрация → план 'free'."""
    plan = service.get_user_plan(test_user)
    assert plan['plan'] == 'free'
    assert plan['is_premium'] is False
    assert plan['ai_max_tokens'] == 2000


def test_user_without_subscription_defaults_to_free(service, db):
    """User with no subscription row → treated as free."""
    cursor = db.execute(
        "INSERT INTO users (email) VALUES (?)", ('noplan@example.com',)
    )
    db.commit()
    user_id = cursor.lastrowid

    plan = service.get_user_plan(user_id)
    assert plan['plan'] == 'free'


# ── Test 2: Free user daily limits ───────────────────────────────────────────

def test_free_user_blocked_after_3_ai_explanations(service, test_user, db):
    """Test 2: 3 AI-разбора → 4-й блокирован."""
    today = datetime.utcnow().date().isoformat()
    db.execute("""
        INSERT OR REPLACE INTO usage_daily (user_id, date, ai_explanations_used)
        VALUES (?, ?, 3)
    """, (test_user, today))
    db.commit()

    can_use, msg = service.can_use_feature(test_user, 'ai_explanation')

    assert can_use is False
    assert '3' in msg or 'лимит' in msg.lower() or 'тариф' in msg.lower()


def test_free_user_not_blocked_at_2_ai(service, test_user, db):
    today = datetime.utcnow().date().isoformat()
    db.execute("""
        INSERT OR REPLACE INTO usage_daily (user_id, date, ai_explanations_used)
        VALUES (?, ?, 2)
    """, (test_user, today))
    db.commit()

    can_use, _ = service.can_use_feature(test_user, 'ai_explanation')
    assert can_use is True


def test_free_user_blocked_after_20_tasks(service, test_user, db):
    today = datetime.utcnow().date().isoformat()
    db.execute("""
        INSERT OR REPLACE INTO usage_daily (user_id, date, tasks_completed)
        VALUES (?, ?, 20)
    """, (test_user, today))
    db.commit()

    can_use, msg = service.can_use_feature(test_user, 'task')
    assert can_use is False
    assert '20' in msg or 'лимит' in msg.lower()


def test_free_user_can_use_task_initially(service, test_user):
    can_use, msg = service.can_use_feature(test_user, 'task')
    assert can_use is True
    assert msg == ''


def test_free_user_can_use_ai_initially(service, test_user):
    can_use, _ = service.can_use_feature(test_user, 'ai_explanation')
    assert can_use is True


# ── Test 3: Activate premium ──────────────────────────────────────────────────

def test_activate_premium(service, test_user):
    """Test 3: активация → план 'premium_monthly'."""
    result = service.activate_premium(test_user, plan='premium_monthly', is_beta=True)

    assert result['plan'] == 'premium_monthly'
    assert result['is_beta'] is True
    assert result['expires_at'] is not None

    plan = service.get_user_plan(test_user)
    assert plan['plan'] == 'premium_monthly'
    assert plan['is_premium'] is True


def test_activate_premium_sets_max_tokens(service, test_user):
    service.activate_premium(test_user, plan='premium_monthly', is_beta=True)
    plan = service.get_user_plan(test_user)
    assert plan['ai_max_tokens'] == 8000


def test_activate_yearly_premium(service, test_user):
    result = service.activate_premium(test_user, plan='premium_yearly', is_beta=True)
    assert result['plan'] == 'premium_yearly'

    plan = service.get_user_plan(test_user)
    assert plan['plan'] == 'premium_yearly'


# ── Test 4: Premium unlimited ─────────────────────────────────────────────────

def test_premium_unlimited_ai(service, premium_user, db):
    """Test 4: 10 разборов подряд → все проходят."""
    today = datetime.utcnow().date().isoformat()
    db.execute("""
        INSERT OR REPLACE INTO usage_daily (user_id, date, ai_explanations_used)
        VALUES (?, ?, 10)
    """, (premium_user, today))
    db.commit()

    can_use, msg = service.can_use_feature(premium_user, 'ai_explanation')
    assert can_use is True


def test_premium_unlimited_tasks(service, premium_user, db):
    today = datetime.utcnow().date().isoformat()
    db.execute("""
        INSERT OR REPLACE INTO usage_daily (user_id, date, tasks_completed)
        VALUES (?, ?, 100)
    """, (premium_user, today))
    db.commit()

    can_use, _ = service.can_use_feature(premium_user, 'task')
    assert can_use is True


# ── Test 5: Premium monthly soft limit ───────────────────────────────────────

def test_premium_monthly_soft_limit(service, premium_user, db):
    """Test 5: 201-й разбор в месяц → блокирован с fair use сообщением."""
    today = datetime.utcnow().date().isoformat()
    db.execute("""
        INSERT OR REPLACE INTO usage_daily (user_id, date, ai_explanations_used)
        VALUES (?, ?, 200)
    """, (premium_user, today))
    db.commit()

    can_use, msg = service.can_use_feature(premium_user, 'ai_explanation')

    assert can_use is False
    assert '200' in msg or 'месяц' in msg.lower() or 'лимит' in msg.lower()


def test_premium_at_199_not_blocked(service, premium_user, db):
    today = datetime.utcnow().date().isoformat()
    db.execute("""
        INSERT OR REPLACE INTO usage_daily (user_id, date, ai_explanations_used)
        VALUES (?, ?, 199)
    """, (premium_user, today))
    db.commit()

    can_use, _ = service.can_use_feature(premium_user, 'ai_explanation')
    assert can_use is True


# ── Test 6: Expired premium falls back to free ────────────────────────────────

def test_expired_premium_fallback_to_free(service, test_user, db):
    """Test 6: истёк expires_at → автоматически free."""
    expired_at = (datetime.utcnow() - timedelta(days=1)).isoformat()
    db.execute("""
        INSERT INTO subscriptions
            (user_id, plan, status, expires_at, is_beta_access)
        VALUES (?, 'premium_monthly', 'active', ?, 1)
    """, (test_user, expired_at))
    db.commit()

    plan = service.get_user_plan(test_user)

    assert plan['plan'] == 'free'
    assert plan['is_premium'] is False
    assert plan['ai_max_tokens'] == 2000


def test_active_premium_not_expired(service, test_user, db):
    future_at = (datetime.utcnow() + timedelta(days=30)).isoformat()
    db.execute("""
        INSERT INTO subscriptions
            (user_id, plan, status, expires_at, is_beta_access)
        VALUES (?, 'premium_monthly', 'active', ?, 1)
    """, (test_user, future_at))
    db.commit()

    plan = service.get_user_plan(test_user)
    assert plan['plan'] == 'premium_monthly'


# ── Test 7: Usage tracking ────────────────────────────────────────────────────

def test_increment_task_usage(service, test_user):
    """Test 7: счётчики правильно увеличиваются."""
    service.increment_usage(test_user, 'task')
    usage = service.get_today_usage(test_user)
    assert usage['tasks_completed'] == 1


def test_increment_ai_usage(service, test_user):
    service.increment_usage(test_user, 'ai_explanation', tokens=500, cost_usd=0.001)
    usage = service.get_today_usage(test_user)
    assert usage['ai_explanations_used'] == 1
    assert usage['tokens_consumed'] == 500


def test_increment_multiple_times(service, test_user):
    for _ in range(5):
        service.increment_usage(test_user, 'task')
    usage = service.get_today_usage(test_user)
    assert usage['tasks_completed'] == 5


def test_get_today_usage_empty(service, test_user):
    usage = service.get_today_usage(test_user)
    assert usage['tasks_completed'] == 0
    assert usage['ai_explanations_used'] == 0


# ── Test 8: Max tokens by plan ────────────────────────────────────────────────

def test_free_max_tokens(service, test_user):
    """Test 8: Free получает 2000."""
    plan = service.get_user_plan(test_user)
    assert plan['ai_max_tokens'] == 2000


def test_premium_max_tokens(service, test_user):
    """Test 8: Premium получает 8000."""
    service.activate_premium(test_user, plan='premium_monthly', is_beta=True)
    plan = service.get_user_plan(test_user)
    assert plan['ai_max_tokens'] == 8000


def test_yearly_premium_max_tokens(service, test_user):
    service.activate_premium(test_user, plan='premium_yearly', is_beta=True)
    plan = service.get_user_plan(test_user)
    assert plan['ai_max_tokens'] == 8000


# ── Cancel subscription ───────────────────────────────────────────────────────

def test_cancel_active_subscription(service, test_user, db):
    service.activate_premium(test_user, plan='premium_monthly', is_beta=True)

    result = service.cancel_subscription(test_user)
    assert result is True

    row = db.execute(
        "SELECT status FROM subscriptions WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (test_user,)
    ).fetchone()
    assert row['status'] == 'cancelled'


def test_cancel_no_subscription(service, test_user):
    result = service.cancel_subscription(test_user)
    assert result is False


# ── Usage for display ─────────────────────────────────────────────────────────

def test_free_user_display(service, test_user, db):
    today = datetime.utcnow().date().isoformat()
    db.execute("""
        INSERT OR REPLACE INTO usage_daily
            (user_id, date, tasks_completed, ai_explanations_used)
        VALUES (?, ?, 5, 2)
    """, (test_user, today))
    db.commit()

    display = service.get_usage_for_display(test_user)

    assert display['tasks']['used'] == 5
    assert display['tasks']['limit'] == 20
    assert display['tasks']['pct'] == 25  # 5/20 * 100

    assert display['ai_today']['used'] == 2
    assert display['ai_today']['limit'] == 3
    assert display['ai_today']['pct'] == 67  # round(2/3*100)


def test_premium_user_display_no_daily_limit(service, premium_user, db):
    today = datetime.utcnow().date().isoformat()
    db.execute("""
        INSERT OR REPLACE INTO usage_daily
            (user_id, date, tasks_completed, ai_explanations_used)
        VALUES (?, ?, 50, 10)
    """, (premium_user, today))
    db.commit()

    display = service.get_usage_for_display(premium_user)

    # Premium has no daily task limit
    assert display['tasks']['limit'] is None
    assert display['tasks']['pct'] is None

    # Premium has no daily AI limit
    assert display['ai_today']['limit'] is None
