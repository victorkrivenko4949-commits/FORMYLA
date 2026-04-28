# -*- coding: utf-8 -*-
"""
Shared pytest fixtures for FORMYLA tests.
Uses in-memory SQLite — no formyla.db is touched.
"""

import sqlite3
import pytest


@pytest.fixture
def db():
    """In-memory SQLite connection with subscription tables."""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            current_plan TEXT DEFAULT 'free',
            plan_expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            payment_method TEXT,
            payment_id TEXT,
            amount_rub INTEGER,
            is_trial INTEGER DEFAULT 0,
            is_beta_access INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE usage_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date DATE NOT NULL,
            tasks_completed INTEGER DEFAULT 0,
            ai_explanations_used INTEGER DEFAULT 0,
            tokens_consumed INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0,
            UNIQUE(user_id, date),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX idx_sub_user ON subscriptions(user_id);
        CREATE INDEX idx_sub_status ON subscriptions(status);
        CREATE INDEX idx_usage_user_date ON usage_daily(user_id, date);
    """)
    conn.commit()

    yield conn
    conn.close()


@pytest.fixture
def service(db):
    """SubscriptionService backed by in-memory sqlite3."""
    from services.subscription import SubscriptionService
    return SubscriptionService(db)


@pytest.fixture
def test_user(db):
    """Creates a test user, returns user_id."""
    cursor = db.execute(
        "INSERT INTO users (email, current_plan) VALUES (?, 'free')",
        ('test@example.com',)
    )
    db.commit()
    return cursor.lastrowid


@pytest.fixture
def premium_user(db, service):
    """User with active Premium subscription."""
    cursor = db.execute(
        "INSERT INTO users (email, current_plan) VALUES (?, 'free')",
        ('premium@example.com',)
    )
    db.commit()
    user_id = cursor.lastrowid
    service.activate_premium(user_id, plan='premium_monthly', is_beta=True)
    return user_id
