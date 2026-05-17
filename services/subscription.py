# -*- coding: utf-8 -*-
"""
SubscriptionService for FORMYLA Free/Premium subscriptions.

Works with two DB connection types:
  1. raw sqlite3.Connection (tests)
  2. SQLAlchemy session (production Flask app)
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

PLAN_LIMITS = {
    'free': {
        'tasks_per_day': 20,
        'tasks_per_day_soft': None,
        'ai_explanations_per_day': 3,
        'ai_explanations_per_month': None,
        'ai_max_tokens': 2000,
        'history_days': 7,
        'price_rub': 0,
        'duration_days': None,
        'display_name': 'Бесплатный',
    },
    'premium_monthly': {
        'tasks_per_day': None,
        'tasks_per_day_soft': 500,
        'ai_explanations_per_day': None,
        'ai_explanations_per_month': 200,
        'ai_max_tokens': 8000,
        'history_days': None,
        'price_rub': 390,
        'duration_days': 30,
        'display_name': 'Premium',
    },
    'premium_yearly': {
        'tasks_per_day': None,
        'tasks_per_day_soft': 500,
        'ai_explanations_per_day': None,
        'ai_explanations_per_month': 300,
        'ai_max_tokens': 8000,
        'history_days': None,
        'price_rub': 2790,
        'duration_days': 365,
        'display_name': 'Premium (год)',
    },
}

_ABUSE_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'logs', 'abuse_alerts.log'
)


def _abuse_log(message: str):
    try:
        os.makedirs(os.path.dirname(_ABUSE_LOG_PATH), exist_ok=True)
        with open(_ABUSE_LOG_PATH, 'a', encoding='utf-8') as f:
            ts = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f'[{ts}] {message}\n')
    except Exception as e:
        logger.warning(f'[ABUSE_LOG] Failed to write: {e}')


class SubscriptionService:
    """
    Subscription management service.
    db=None -> lazy SQLAlchemy (production)
    db=sqlite3.Connection -> tests
    """

    def __init__(self, db=None):
        self._db_raw = db

    @property
    def _is_raw_sqlite(self) -> bool:
        import sqlite3
        return self._db_raw is not None and isinstance(self._db_raw, sqlite3.Connection)

    @property
    def db(self):
        if self._db_raw is not None:
            return self._db_raw
        from models import db as _db
        return _db.session

    def _execute(self, query: str, params=()):
        if self._is_raw_sqlite:
            return self._db_raw.execute(query, params)
        from sqlalchemy import text as _text
        named_q, named_p = self._qmark_to_named(query, params)
        return self.db.execute(_text(named_q), named_p)

    @staticmethod
    def _qmark_to_named(query: str, params: tuple):
        param_dict = {}
        result = query
        for i, value in enumerate(params):
            result = result.replace('?', f':p{i}', 1)
            param_dict[f'p{i}'] = value
        return result, param_dict

    def _commit(self):
        if self._is_raw_sqlite:
            self._db_raw.commit()
        # SQLAlchemy: do NOT call db.session.commit() here.
        # Flask-SQLAlchemy manages transactions per request.
        # Calling commit() here causes "database is locked" with APScheduler.

    def _fetchone(self, query: str, params=()):
        result = self._execute(query, params)
        if self._is_raw_sqlite:
            return result.fetchone()
        row = result.fetchone()
        return dict(row._mapping) if row else None

    def _fetchall(self, query: str, params=()):
        result = self._execute(query, params)
        if self._is_raw_sqlite:
            return result.fetchall()
        return [dict(r._mapping) for r in result.fetchall()]

    def _row_get(self, row, key, default=None):
        if row is None:
            return default
        try:
            return row[key]
        except (KeyError, IndexError):
            return default

    # ── Get user plan ─────────────────────────────────────────────────────────

    def get_user_plan(self, user_id: int) -> dict:
        now_iso = datetime.utcnow().isoformat()
        row = self._fetchone("""
            SELECT plan, status, expires_at, is_beta_access, is_trial
            FROM subscriptions
            WHERE user_id = ?
              AND status = 'active'
              AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY
                CASE WHEN plan LIKE 'premium%' THEN 0 ELSE 1 END,
                id DESC
            LIMIT 1
        """, (user_id, now_iso))

        plan_key = 'free'
        expires_at = None
        is_beta = False

        if row:
            plan_val = self._row_get(row, 'plan', 'free')
            if plan_val in ('premium_monthly', 'premium_yearly'):
                plan_key = plan_val
                expires_at = self._row_get(row, 'expires_at')
                is_beta = bool(self._row_get(row, 'is_beta_access', 0))

        limits = PLAN_LIMITS.get(plan_key, PLAN_LIMITS['free'])
        return {
            'plan': plan_key,
            'display_name': limits['display_name'],
            'expires_at': expires_at,
            'is_premium': plan_key != 'free',
            'is_beta_access': is_beta,
            'ai_max_tokens': limits['ai_max_tokens'],
            'limits': limits,
        }

    # ── Check feature limits ──────────────────────────────────────────────────

    def can_use_feature(self, user_id: int, feature: str) -> tuple:
        plan_info = self.get_user_plan(user_id)
        plan_key = plan_info['plan']
        limits = plan_info['limits']
        usage = self.get_today_usage(user_id)

        if feature == 'task':
            daily_limit = limits.get('tasks_per_day')
            soft_limit = limits.get('tasks_per_day_soft')
            used = usage.get('tasks_completed', 0)

            if daily_limit is not None and used >= daily_limit:
                msg = (f"Бесплатный тариф: {daily_limit} задач в день. "
                       f"Оформите Premium для безлимита.")
                logger.info(f'[LIMIT] User {user_id} blocked on task ({used}/{daily_limit} used)')
                return False, msg

            if soft_limit is not None and used >= soft_limit:
                msg = (f"Достигнут дневной лимит {soft_limit} задач (fair use). "
                       f"Попробуйте завтра.")
                return False, msg

            return True, ''

        elif feature == 'ai_explanation':
            daily_limit = limits.get('ai_explanations_per_day')
            used_today = usage.get('ai_explanations_used', 0)

            if daily_limit is not None and used_today >= daily_limit:
                msg = (f"Бесплатный тариф: {daily_limit} разбора в день. "
                       f"Оформите Premium для безлимита.")
                logger.info(f'[LIMIT] User {user_id} blocked on ai_explanation '
                            f'({used_today}/{daily_limit} used)')
                return False, msg

            monthly_limit = limits.get('ai_explanations_per_month')
            if monthly_limit is not None:
                month_usage = self.get_month_usage(user_id)
                used_month = month_usage.get('ai_explanations_used', 0)

                if used_today > 50:
                    _abuse_log(f'[ABUSE] User {user_id} used {used_today} AI explanations today '
                               f'(plan={plan_key})')

                if used_month >= monthly_limit:
                    msg = (f"Достигнут месячный лимит {monthly_limit} AI-разборов (fair use). "
                           f"Лимит обновится в следующем месяце.")
                    logger.info(f'[LIMIT] User {user_id} soft-blocked on ai_explanation '
                                f'({used_month}/{monthly_limit} monthly)')
                    return False, msg

            return True, ''

        logger.warning(f'[SUBSCRIPTION] Unknown feature: {feature}')
        return True, ''

    # ── Activate premium ──────────────────────────────────────────────────────

    def activate_premium(self, user_id: int, plan: str = 'premium_monthly',
                         payment_id: Optional[str] = None, is_beta: bool = True,
                         amount_rub: Optional[int] = None) -> dict:
        if plan not in PLAN_LIMITS:
            raise ValueError(f'Unknown plan: {plan}')

        limits = PLAN_LIMITS[plan]
        duration_days = limits.get('duration_days', 30)
        now = datetime.utcnow()
        expires_at = now + timedelta(days=duration_days)

        self._execute("""
            UPDATE subscriptions
            SET status = 'superseded'
            WHERE user_id = ? AND status = 'active'
        """, (user_id,))

        self._execute("""
            INSERT INTO subscriptions
                (user_id, plan, status, started_at, expires_at,
                 payment_id, amount_rub, is_beta_access, created_at)
            VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?)
        """, (
            user_id, plan,
            now.isoformat(), expires_at.isoformat(),
            payment_id,
            amount_rub or (0 if is_beta else limits['price_rub']),
            1 if is_beta else 0,
            now.isoformat(),
        ))

        try:
            self._execute("""
                UPDATE users
                SET current_plan = ?, plan_expires_at = ?
                WHERE id = ?
            """, (plan, expires_at.isoformat(), user_id))
        except Exception:
            pass

        self._commit()

        beta_str = ' (beta)' if is_beta else ''
        logger.info(f'[SUBSCRIPTION] User {user_id} activated {plan}{beta_str}')

        return {
            'plan': plan,
            'display_name': limits['display_name'],
            'expires_at': expires_at.isoformat(),
            'is_beta': is_beta,
        }

    # ── Cancel subscription ───────────────────────────────────────────────────

    def cancel_subscription(self, user_id: int) -> bool:
        row = self._fetchone("""
            SELECT id, expires_at FROM subscriptions
            WHERE user_id = ? AND status = 'active'
            ORDER BY id DESC LIMIT 1
        """, (user_id,))

        if not row:
            return False

        sub_id = self._row_get(row, 'id')
        expires = self._row_get(row, 'expires_at')

        self._execute("""
            UPDATE subscriptions SET status = 'cancelled' WHERE id = ?
        """, (sub_id,))

        self._commit()
        logger.info(f'[SUBSCRIPTION] User {user_id} cancelled (access until {expires})')
        return True

    # ── Usage tracking ────────────────────────────────────────────────────────

    def get_today_usage(self, user_id: int) -> dict:
        today = datetime.utcnow().date().isoformat()
        row = self._fetchone("""
            SELECT tasks_completed, ai_explanations_used, tokens_consumed, cost_usd
            FROM usage_daily
            WHERE user_id = ? AND date = ?
        """, (user_id, today))

        if row:
            return {
                'tasks_completed': self._row_get(row, 'tasks_completed', 0) or 0,
                'ai_explanations_used': self._row_get(row, 'ai_explanations_used', 0) or 0,
                'tokens_consumed': self._row_get(row, 'tokens_consumed', 0) or 0,
                'cost_usd': self._row_get(row, 'cost_usd', 0.0) or 0.0,
                'date': today,
            }
        return {'tasks_completed': 0, 'ai_explanations_used': 0,
                'tokens_consumed': 0, 'cost_usd': 0.0, 'date': today}

    def get_month_usage(self, user_id: int) -> dict:
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        row = self._fetchone("""
            SELECT
                SUM(tasks_completed) as tasks_completed,
                SUM(ai_explanations_used) as ai_explanations_used,
                SUM(tokens_consumed) as tokens_consumed,
                SUM(cost_usd) as cost_usd
            FROM usage_daily
            WHERE user_id = ? AND date >= ?
        """, (user_id, month_start.date().isoformat()))

        if row:
            return {
                'tasks_completed': self._row_get(row, 'tasks_completed', 0) or 0,
                'ai_explanations_used': self._row_get(row, 'ai_explanations_used', 0) or 0,
                'tokens_consumed': self._row_get(row, 'tokens_consumed', 0) or 0,
                'cost_usd': self._row_get(row, 'cost_usd', 0.0) or 0.0,
                'month': month_start.strftime('%Y-%m'),
            }
        return {'tasks_completed': 0, 'ai_explanations_used': 0,
                'tokens_consumed': 0, 'cost_usd': 0.0,
                'month': month_start.strftime('%Y-%m')}

    def increment_usage(self, user_id: int, feature: str,
                        tokens: int = 0, cost_usd: float = 0.0):
        today = datetime.utcnow().date().isoformat()

        self._execute("""
            INSERT OR IGNORE INTO usage_daily (user_id, date)
            VALUES (?, ?)
        """, (user_id, today))

        if feature == 'task':
            self._execute("""
                UPDATE usage_daily
                SET tasks_completed = tasks_completed + 1
                WHERE user_id = ? AND date = ?
            """, (user_id, today))
        elif feature == 'ai_explanation':
            self._execute("""
                UPDATE usage_daily
                SET ai_explanations_used = ai_explanations_used + 1,
                    tokens_consumed = tokens_consumed + ?,
                    cost_usd = cost_usd + ?
                WHERE user_id = ? AND date = ?
            """, (tokens, cost_usd, user_id, today))

        try:
            self._commit()
        except Exception as e:
            logger.warning(f'[SUBSCRIPTION] increment_usage commit failed: {e}')

    # ── Display helpers ───────────────────────────────────────────────────────

    def get_usage_for_display(self, user_id: int) -> dict:
        plan_info = self.get_user_plan(user_id)
        limits = plan_info['limits']
        today_usage = self.get_today_usage(user_id)
        month_usage = self.get_month_usage(user_id)

        tasks_used = today_usage['tasks_completed']
        tasks_limit = limits.get('tasks_per_day')
        tasks_pct = (min(100, round(tasks_used / tasks_limit * 100))
                     if tasks_limit else None)

        ai_used_today = today_usage['ai_explanations_used']
        ai_limit_day = limits.get('ai_explanations_per_day')
        ai_pct_day = (min(100, round(ai_used_today / ai_limit_day * 100))
                      if ai_limit_day else None)

        ai_used_month = month_usage['ai_explanations_used']
        ai_limit_month = limits.get('ai_explanations_per_month')
        ai_pct_month = (min(100, round(ai_used_month / ai_limit_month * 100))
                        if ai_limit_month else None)

        return {
            'plan': plan_info,
            'tasks': {'used': tasks_used, 'limit': tasks_limit, 'pct': tasks_pct},
            'ai_today': {'used': ai_used_today, 'limit': ai_limit_day, 'pct': ai_pct_day},
            'ai_month': {'used': ai_used_month, 'limit': ai_limit_month, 'pct': ai_pct_month},
        }

    def get_top_users_by_usage(self, days: int = 30, limit: int = 20) -> list:
        since = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
        rows = self._fetchall("""
            SELECT
                ud.user_id,
                u.email,
                u.current_plan,
                SUM(ud.tasks_completed) as total_tasks,
                SUM(ud.ai_explanations_used) as total_ai,
                SUM(ud.tokens_consumed) as total_tokens,
                SUM(ud.cost_usd) as total_cost,
                COUNT(DISTINCT ud.date) as active_days
            FROM usage_daily ud
            LEFT JOIN users u ON u.id = ud.user_id
            WHERE ud.date >= ?
            GROUP BY ud.user_id
            ORDER BY total_ai DESC
            LIMIT ?
        """, (since, limit))

        result = []
        for r in rows:
            result.append({
                'user_id': self._row_get(r, 'user_id', 0),
                'email': self._row_get(r, 'email', 'unknown'),
                'plan': self._row_get(r, 'current_plan', 'free'),
                'total_tasks': self._row_get(r, 'total_tasks', 0) or 0,
                'total_ai': self._row_get(r, 'total_ai', 0) or 0,
                'total_tokens': self._row_get(r, 'total_tokens', 0) or 0,
                'total_cost': round(self._row_get(r, 'total_cost', 0) or 0, 4),
                'active_days': self._row_get(r, 'active_days', 0) or 0,
            })
        return result


# ── Global singleton (lazy init for production) ───────────────────────────────

_service_instance: Optional[SubscriptionService] = None


def get_subscription_service() -> SubscriptionService:
    """Returns global SubscriptionService instance (SQLAlchemy in production)."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SubscriptionService()
    return _service_instance
