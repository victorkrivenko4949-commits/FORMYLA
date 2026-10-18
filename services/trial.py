# -*- coding: utf-8 -*-
"""TRIAL_V1 (18.10.2026) — триал 14 дней при регистрации + доступ Основателей до 31.01.2027.

  * users.trial_until (ALTER на лету, как acq_* в services/funnel.py)
  * выдача: сигнал flask_login.user_logged_in для пользователя моложе 2 минут;
    защита от повторной выдачи — таблица trial_grants (email / telegram_id UNIQUE)
  * User.is_trial_active() — метод добавляется в класс User при install();
    его уже проверяет method_week/paywall.user_has_paid_access через getattr
  * Основатели (services.billing_plans.is_founder) считаются активными до FOUNDER_FREE_UNTIL,
    если нет платной подписки — так paywall пропускает их бесплатно до 31.01.2027
  * метка «Premium до DD.MM» в шапке — инжект after_request (TRIAL_BADGE=1)

Env: TRIAL_ENABLED=1, TRIAL_DAYS=14, FOUNDER_FREE_UNTIL=2027-01-31, TRIAL_BADGE=1.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import date, datetime, timedelta

from flask import request
from flask_login import current_user, user_logged_in
from sqlalchemy import text

logger = logging.getLogger(__name__)

ENABLED = os.environ.get('TRIAL_ENABLED', '1') != '0'
FRESH_WINDOW = timedelta(minutes=2)
INJECT_MARK = 'id="ft-plan-badge"'


def trial_days() -> int:
    try:
        return max(0, int(os.environ.get('TRIAL_DAYS', '14') or 14))
    except ValueError:
        return 14


def founder_free_until() -> date:
    try:
        return date.fromisoformat(os.environ.get('FOUNDER_FREE_UNTIL', '2027-01-31'))
    except ValueError:
        return date(2027, 1, 31)


def _db():
    from models import db
    return db


def _pg() -> bool:
    try:
        return _db().engine.dialect.name == 'postgresql'
    except Exception:
        return False


_ready = False


def ensure_schema() -> None:
    global _ready
    if _ready or not ENABLED:
        return
    db = _db()
    pg = _pg()
    serial = 'SERIAL PRIMARY KEY' if pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    ts = 'TIMESTAMP NOT NULL DEFAULT NOW()' if pg else 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP'
    try:
        if pg:
            db.session.execute(text('ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_until TIMESTAMP'))
        else:
            cols = [r[1] for r in db.session.execute(text('PRAGMA table_info(users)')).fetchall()]
            if 'trial_until' not in cols:
                db.session.execute(text('ALTER TABLE users ADD COLUMN trial_until TIMESTAMP'))
        db.session.execute(text(f"""CREATE TABLE IF NOT EXISTS trial_grants (
            id {serial}, identity VARCHAR(80) NOT NULL UNIQUE, user_id INTEGER, granted_at {ts})"""))
        db.session.commit()
        _ready = True
    except Exception as e:
        db.session.rollback()
        logger.warning('trial.ensure_schema: %r', e)


def _identities(user) -> list:
    out = []
    email = (getattr(user, 'email', '') or '').strip().lower()
    if email and not email.endswith('@telegram.formyla.local'):
        out.append('e:' + hashlib.sha256(email.encode()).hexdigest()[:40])
    tg = getattr(user, 'telegram_id', None)
    if tg:
        out.append('tg:' + str(tg))
    return out


def _to_dt(v):
    if v is None or isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v))
    except Exception:
        return None


def is_trial_active(user) -> bool:
    """Триал активен ИЛИ Основатель в бесплатном периоде (без учёта платной подписки)."""
    if user is None or not ENABLED:
        return False
    tu = _to_dt(getattr(user, 'trial_until', None))
    if tu and tu > datetime.utcnow():
        return True
    try:
        from services.billing_plans import is_founder
        if is_founder(user) and (datetime.utcnow() + timedelta(hours=3)).date() <= founder_free_until():
            return True
    except Exception:
        pass
    return False


def trial_info(user) -> dict:
    """Что показывать в шапке: {'kind': 'paid'|'founder'|'trial'|None, 'until': date|None, 'label': str}."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return {'kind': None, 'until': None, 'label': ''}
    try:
        from services.subscription import get_subscription_service
        plan = get_subscription_service().get_user_plan(user.id)
        if plan.get('is_premium') and not plan.get('is_beta_access'):
            until = _to_dt(plan.get('expires_at'))
            return {'kind': 'paid', 'until': until.date() if until else None,
                    'label': f"{plan.get('display_name')}" + (f" до {until.strftime('%d.%m')}" if until else '')}
    except Exception:
        pass
    try:
        from services.billing_plans import is_founder
        if is_founder(user):
            u = founder_free_until()
            return {'kind': 'founder', 'until': u, 'label': f"Основатель · Premium до {u.strftime('%d.%m')}"}
    except Exception:
        pass
    tu = _to_dt(getattr(user, 'trial_until', None))
    if tu and tu > datetime.utcnow():
        return {'kind': 'trial', 'until': tu.date(), 'label': f"Premium до {tu.strftime('%d.%m')}"}
    return {'kind': None, 'until': None, 'label': ''}


def grant_trial(user, days: int | None = None) -> bool:
    """Выдать триал, если ещё не выдавался на этот e-mail/telegram. Возвращает True при выдаче."""
    if not ENABLED or user is None:
        return False
    days = trial_days() if days is None else days
    if days <= 0:
        return False
    try:
        from services.billing_plans import is_founder
        if is_founder(user):
            return False  # у Основателя свой срок — не перекрываем
    except Exception:
        pass
    if _to_dt(getattr(user, 'trial_until', None)):
        return False
    db = _db()
    try:
        ensure_schema()
        for ident in _identities(user):
            if db.session.execute(text('SELECT 1 FROM trial_grants WHERE identity = :i'), {'i': ident}).first():
                return False
        until = datetime.utcnow() + timedelta(days=days)
        db.session.execute(text('UPDATE users SET trial_until = :t WHERE id = :u AND trial_until IS NULL'),
                           {'t': until, 'u': user.id})
        for ident in _identities(user) or [f'u:{user.id}']:
            db.session.execute(text('INSERT INTO trial_grants (identity, user_id) VALUES (:i, :u)'),
                               {'i': ident, 'u': user.id})
        db.session.commit()
        try:
            setattr(user, 'trial_until', until)
        except Exception:
            pass
        try:
            from services.funnel import track
            track('trial_granted', {'days': days}, user_id=user.id)
        except Exception:
            pass
        logger.info('trial granted user=%s until=%s', user.id, until)
        return True
    except Exception as e:
        db.session.rollback()
        logger.warning('trial.grant_trial: %r', e)
        return False


def _on_login(sender, user, **extra):
    try:
        created = getattr(user, 'created_at', None)
        if created and datetime.utcnow() - created <= FRESH_WINDOW:
            grant_trial(user)
    except Exception as e:
        logger.warning('trial._on_login: %r', e)


def _badge_html(info: dict) -> str:
    color = {'paid': '#3ecf8e', 'founder': '#a78bfa', 'trial': '#38bdf8'}.get(info['kind'], '#94a3b8')
    return (f'<a id="ft-plan-badge" href="/subscribe?from=profile" title="Подписка" style="position:fixed;top:10px;right:14px;'
            f'z-index:29000;padding:5px 10px;border-radius:999px;font:600 12px/1 Inter,system-ui,sans-serif;'
            f'background:rgba(15,23,42,.85);color:{color};border:1px solid {color}55;text-decoration:none;'
            f'backdrop-filter:blur(6px);">{info["label"]}</a>')


def install(app) -> None:
    if not ENABLED or app.extensions.get('trial_installed'):
        return
    app.extensions['trial_installed'] = True
    try:
        with app.app_context():
            ensure_schema()
    except Exception as e:
        logger.warning('trial: ensure_schema at startup failed: %r', e)
    try:
        from models import User
        if not hasattr(User, 'is_trial_active'):
            User.is_trial_active = lambda self: is_trial_active(self)  # noqa: E731
    except Exception as e:
        logger.warning('trial: cannot attach User.is_trial_active: %r', e)
    user_logged_in.connect(_on_login, app)

    @app.context_processor
    def _inject_trial():
        try:
            return {'trial_info': trial_info(current_user)}
        except Exception:
            return {'trial_info': {'kind': None, 'until': None, 'label': ''}}

    if os.environ.get('TRIAL_BADGE', '1') != '0':
        @app.after_request
        def _badge(resp):
            try:
                if (resp.status_code != 200 or resp.mimetype != 'text/html' or resp.direct_passthrough
                        or request.path.startswith(('/admin/', '/static/', '/intake'))
                        or not getattr(current_user, 'is_authenticated', False)):
                    return resp
                info = trial_info(current_user)
                if not info['kind']:
                    return resp
                html = resp.get_data(as_text=True)
                if INJECT_MARK in html or '</body>' not in html:
                    return resp
                idx = html.rfind('</body>')
                resp.set_data(html[:idx] + _badge_html(info) + html[idx:])
            except Exception as e:
                logger.debug('trial badge skipped: %r', e)
            return resp
    logger.info('TRIAL_V1 registered (days=%s, founder_free_until=%s)', trial_days(), founder_free_until())
