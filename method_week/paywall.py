# -*- coding: utf-8 -*-
"""Paywall платных разделов FORMYLA (запуск — начало ноября 2026).

Платные: задачи дня, метод недели, генератор чертежей, ИИ-тьютор, куратор.
Доступ есть у: Premium-подписки (services.subscription), активного триала
(User.is_trial_active), администраторов (id=1 / ADMIN_EMAILS), а также у
e-mail из PAYWALL_WHITELIST. Переменные окружения:

  PAYWALL_ENABLED=1|0            (по умолчанию 0 — ВЫКЛЮЧЕН; включить вручную к ноябрю)
  PAYWALL_START_DATE=2026-11-01  (до этой даты всё бесплатно даже при ENABLED=1)
  PAYWALL_PREFIXES=/method_week,/geometry/draw,/figures/generate  (задачи дня/тьютор — мягкие лимиты)
  PAYWALL_WHITELIST=a@b.ru,c@d.ru
  PAYWALL_UPGRADE_URL=/subscribe
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import List, Optional

from flask import jsonify, redirect, request

logger = logging.getLogger(__name__)

# SOFT_LIMITS_V1 (18.10.2026): /daily_tasks, /api/tutor и /prep больше НЕ за жёстким paywall —
# там мягкие лимиты (services/soft_limits.py). Жёсткий paywall только на новых функциях.
DEFAULT_PREFIXES = '/method_week,/geometry/draw,/figures/generate'
# служебные пути внутри платных разделов, которые нужны фронту для показа paywall
ALWAYS_OPEN_SUFFIXES = ('/job_status',)


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or v == '':
        return default
    return v.strip().lower() in ('1', 'true', 'yes', 'on')


def paywall_active(today: Optional[date] = None) -> bool:
    if not _env_bool('PAYWALL_ENABLED', False):
        return False
    start = os.environ.get('PAYWALL_START_DATE', '2026-11-01').strip()
    try:
        start_d = date.fromisoformat(start)
    except ValueError:
        start_d = date(2026, 11, 1)
    return (today or date.today()) >= start_d


def paid_prefixes() -> List[str]:
    raw = os.environ.get('PAYWALL_PREFIXES', DEFAULT_PREFIXES)
    return [p.strip() for p in raw.split(',') if p.strip()]


def user_has_paid_access(user) -> bool:
    """True, если пользователю можно показывать платные разделы."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    uid = getattr(user, 'id', None)
    email = (getattr(user, 'email', '') or '').strip().lower()
    admin_emails = {e.strip().lower() for e in os.environ.get('ADMIN_EMAILS', '').split(',') if e.strip()}
    if uid == 1 or (email and email in admin_emails):
        return True
    whitelist = {e.strip().lower() for e in os.environ.get('PAYWALL_WHITELIST', '').split(',') if e.strip()}
    if email and email in whitelist:
        return True
    for meth in ('has_active_subscription', 'is_trial_active'):
        fn = getattr(user, meth, None)
        if callable(fn):
            try:
                if fn():
                    return True
            except Exception:
                pass
    try:
        from services.subscription import get_subscription_service
        if get_subscription_service().get_user_plan(uid).get('is_premium'):
            return True
    except Exception as exc:
        logger.warning("paywall: subscription check failed user=%s: %s (fail open)", uid, exc)
        return True
    return False



def _upgrade_price_label(user=None) -> str:
    """Цена для сообщения paywall — из каталога тарифов, не хардкод."""
    try:
        from services.billing_plans import is_founder, price_for
        return f"{price_for('student_month', is_founder(user))} руб/мес"
    except Exception:
        try:
            from services.subscription import PLAN_LIMITS
            return f"{PLAN_LIMITS['premium_monthly']['price_rub']} руб/мес"
        except Exception:
            return '390 руб/мес'


def _is_paid_path(path: str) -> bool:
    if path.endswith(ALWAYS_OPEN_SUFFIXES):
        return False
    for p in paid_prefixes():
        if path == p or path.startswith(p.rstrip('/') + '/'):
            return True
    return False


def _wants_json() -> bool:
    if request.is_json:
        return True
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept and 'text/html' not in accept


def install_paywall(app) -> None:
    @app.before_request
    def _paywall_guard():
        try:
            path = request.path or ''
            if not _is_paid_path(path):
                return None
            if not paywall_active():
                return None
            from flask_login import current_user
            if not getattr(current_user, 'is_authenticated', False):
                return None  # login_required сам разберётся
            if user_has_paid_access(current_user):
                return None
            upgrade = os.environ.get('PAYWALL_UPGRADE_URL', '/subscribe')
            if _wants_json() or request.method != 'GET':
                return jsonify({
                    'error': 'payment_required',
                    'message': 'Этот раздел доступен по подписке Premium.',
                    'upgrade_url': upgrade,
                    'upgrade_price': _upgrade_price_label(current_user),
                }), 402
            return redirect("%s?from=%s" % (upgrade, path))
        except Exception as exc:  # pragma: no cover — paywall никогда не роняет сайт
            logger.error("paywall: guard error: %s (fail open)", exc)
            return None

    logger.info("paywall installed: enabled=%s start=%s prefixes=%s",
                _env_bool('PAYWALL_ENABLED', False),
                os.environ.get('PAYWALL_START_DATE', '2026-11-01'), paid_prefixes())
