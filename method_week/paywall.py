# -*- coding: utf-8 -*-
"""Paywall платных разделов FORMYLA (включён 28.10.2026).

Платные: метод недели, генератор чертежей, ИИ-тьютор, адаптивный тест
(/probniks), каталог методов (/olympiads/methods).
Задачи дня остаются открытыми в бесплатной версии, но с лимитом
(по умолчанию 1 задача в день — services.limits).
Доступ есть у: Premium-подписки (services.subscription), активного триала
(User.is_trial_active), администраторов (id=1 / ADMIN_EMAILS), а также у
e-mail из PAYWALL_WHITELIST. Переменные окружения:

  PAYWALL_ENABLED=1|0            (по умолчанию 1 — ВКЛЮЧЁН; 0 = всё открыть)
  PAYWALL_START_DATE=2026-10-01  (до этой даты всё бесплатно даже при ENABLED=1)
  PAYWALL_PREFIXES=/method_week,/geometry/draw,/figures/generate,/api/tutor,/probniks,/olympiads/methods
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

# Префиксы платных разделов. Задачи дня сюда НЕ входят: в бесплатной
# версии они доступны с дневным лимитом (services.limits, 1 задача/день).
# /prep/probe не гейтим: срез-тест завязан на цикл задач дня.
DEFAULT_PREFIXES = '/method_week,/geometry/draw,/figures/generate,/api/tutor,/probniks,/olympiads/methods,/olympiad-test,/olymp-catalog/api/tutor'

# Понятные названия разделов — для сообщения «недоступно в бесплатной версии»
FEATURE_LABELS = {
    '/probniks': 'Адаптивный тест',
    '/olympiad-test': 'Адаптивный тест',
    '/olympiads/methods': 'Каталог методов',
    '/geometry/draw': 'Генератор чертежей',
    '/figures/generate': 'Генератор чертежей',
    '/api/tutor': 'ИИ-тьютор',
    '/olymp-catalog/api/tutor': 'ИИ-тьютор',
    '/method_week': 'Метод недели',
}


def _feature_label(path: str) -> str:
    """Человекочитаемое название раздела по пути (для баннера на /subscribe)."""
    for prefix, label in FEATURE_LABELS.items():
        if path == prefix or path.startswith(prefix + '/') or path.startswith(prefix + '?'):
            return label
    return ''


# служебные пути внутри платных разделов, которые нужны фронту для показа paywall
ALWAYS_OPEN_SUFFIXES = ('/job_status',)


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or v == '':
        return default
    return v.strip().lower() in ('1', 'true', 'yes', 'on')


def paywall_active(today: Optional[date] = None) -> bool:
    # ВКЛЮЧЁН по умолчанию (28.10.2026): бесплатные пользователи видят
    # закрытые разделы и лимит задач дня. PAYWALL_ENABLED=0 — аварийное
    # отключение без деплоя.
    if not _env_bool('PAYWALL_ENABLED', True):
        return False
    start = os.environ.get('PAYWALL_START_DATE', '2026-10-01').strip()
    try:
        start_d = date.fromisoformat(start)
    except ValueError:
        start_d = date(2026, 10, 1)
    return (today or date.today()) >= start_d


def paid_prefixes() -> List[str]:
    raw = os.environ.get('PAYWALL_PREFIXES', DEFAULT_PREFIXES)
    return [p.strip() for p in raw.split(',') if p.strip()]


def user_has_paid_access(user) -> bool:
    """True, если пользователю можно показывать платные разделы.

    FOUNDERS_V1: источник истины — services.access.resolve_access
    (paid → founder → trial → free). User.is_trial_active() больше НЕ
    используется: он всегда True и пропускал всех. Ошибка проверки —
    fail-closed (платный доступ при сомнении не выдаётся).
    """
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
    try:
        from services.access import resolve_access
        source, _ = resolve_access(user)
        return source in ('paid', 'founder', 'trial')
    except Exception as exc:
        logger.error("paywall: access check failed user=%s: %s (fail closed)", uid, exc)
        return False


def _is_paid_path(path: str) -> bool:
    if path.endswith(ALWAYS_OPEN_SUFFIXES):
        return False
    for p in paid_prefixes():
        if path == p or path.startswith(p.rstrip('/') + '/'):
            return True
    return False


def _wants_json() -> bool:
    if _env_bool('PAYWALL_JSON_HINT', False):
        return True
    if request.is_json:
        return True
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept and 'text/html' not in accept


def _upgrade_price_label(user) -> str:
    try:
        from services.billing.catalog import upgrade_price_label
        return upgrade_price_label(user)
    except Exception:  # каталог не загрузился — paywall не роняем
        return '490 ₽ за 30 дней'


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
            label = _feature_label(path)
            msg = ('Раздел «%s» сейчас недоступен в бесплатной версии — откройте его с Premium.' % label
                   if label else 'Этот раздел доступен по подписке Premium.')
            if _wants_json() or request.method != 'GET':
                return jsonify({
                    'error': 'payment_required',
                    'message': msg,
                    'upgrade_url': upgrade,
                    'upgrade_price': _upgrade_price_label(current_user),
                }), 402
            sep = '&' if '?' in upgrade else '?'
            url = "%s%sfrom=%s" % (upgrade, sep, path)
            if label:
                url += "&feature=%s" % label
            return redirect(url)
        except Exception as exc:  # pragma: no cover — граница доступа
            # fail-CLOSED: платный раздел при сбое guard'а не открывается
            # «на всякий случай». Лог + 503, доступ не выдаём.
            logger.error("paywall: guard error: %s (fail closed)", exc)
            try:
                return ("Раздел временно недоступен, попробуйте позже.", 503)
            except Exception:
                return None

    logger.info("paywall installed: enabled=%s start=%s prefixes=%s",
                _env_bool('PAYWALL_ENABLED', True),
                os.environ.get('PAYWALL_START_DATE', '2026-10-01'), paid_prefixes())
