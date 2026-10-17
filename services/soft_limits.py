# -*- coding: utf-8 -*-
"""SOFT_LIMITS_V1 (18.10.2026) — мягкие лимиты Free вместо стены.

Free: FREE_TASKS_PER_DAY задач дня (деф. 3) и FREE_AI_PER_DAY ИИ-разборов (деф. 1) в сутки (МСК).
Лимиты действуют только если:
  * paywall активен (PAYWALL_ENABLED=1 и дата ≥ PAYWALL_START_DATE — см. method_week/paywall.py),
  * пользователь в A/B-когорте (services/ab.py, PAYWALL_AB),
  * у пользователя нет платного доступа (paywall.user_has_paid_access: подписка, триал, Основатель, админ).

Что НЕ блокируется (красные линии): GET /daily_tasks/ (дашборд), /prep, задачи из долга
(debt_status='active'), уже отвеченные задачи, начатый пробник, /api/tutor для платных.

Реализация без правки daily_tasks/routes.py: оборачиваем view-функции по url_map
(как services/funnel.py): POST /daily_tasks/<id>/submit и /submit_ai → при превышении
402 {error:'limit', upgrade_url, html}; GET /daily_tasks/<id> → страница экрана лимита.
ИИ-тьютор: POST /api/tutor/* → can_use_feature('ai_explanation') + increment_usage после ответа.

Откат: SOFT_LIMITS_ENABLED=0 или PAYWALL_AB=0.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from flask import jsonify, render_template, request
from flask_login import current_user
from sqlalchemy import text

logger = logging.getLogger(__name__)

ENABLED = os.environ.get('SOFT_LIMITS_ENABLED', '1') != '0'
UPGRADE_URL = '/subscribe?from=daily_limit'


def free_tasks() -> int:
    try:
        return max(1, int(os.environ.get('FREE_TASKS_PER_DAY', '3') or 3))
    except ValueError:
        return 3


def free_ai() -> int:
    try:
        return max(0, int(os.environ.get('FREE_AI_PER_DAY', '1') or 1))
    except ValueError:
        return 1


def streak_required(n_available: int | None = None) -> int:
    """Сколько верных нужно для засчитанного дня при лимите N (правило ≥80%).
    Для N=3: 80% = 2.4 → округляем ВНИЗ до 2 из 3, чтобы не рвать серии у Free
    (3 из 3 означало бы, что одна ошибка ломает серию — это хуже, чем старое правило 4 из 5)."""
    n = n_available or free_tasks()
    return max(1, int(0.8 * n))


def _db():
    from models import db
    return db


def _msk_day_bounds_utc():
    now_msk = datetime.utcnow() + timedelta(hours=3)
    start_msk = datetime(now_msk.year, now_msk.month, now_msk.day)
    return start_msk - timedelta(hours=3), start_msk + timedelta(days=1) - timedelta(hours=3)


def limits_apply(user) -> bool:
    """Нужно ли вообще проверять лимиты для этого пользователя."""
    if not ENABLED or user is None or not getattr(user, 'is_authenticated', False):
        return False
    try:
        from method_week.paywall import paywall_active, user_has_paid_access
        if not paywall_active():
            return False
        if user_has_paid_access(user):
            return False
    except Exception as e:
        logger.warning('soft_limits: paywall check failed (%r) — fail open', e)
        return False
    try:
        from services.ab import in_limits_cohort
        return in_limits_cohort(user)
    except Exception:
        return False


def tasks_answered_today(user_id: int) -> int:
    """Задач дня, отвеченных сегодня (МСК), без долга."""
    s, e = _msk_day_bounds_utc()
    try:
        row = _db().session.execute(text("""
            SELECT COUNT(*) FROM daily_task_items i JOIN daily_task_sets st ON st.id = i.daily_set_id
            WHERE st.user_id = :u AND i.answered_at IS NOT NULL AND i.answered_at >= :s AND i.answered_at < :e
              AND (i.debt_status IS NULL OR i.debt_status = '')
        """), {'u': user_id, 's': s, 'e': e}).first()
        return int(row[0] or 0) if row else 0
    except Exception as e:
        _db().session.rollback()
        logger.warning('soft_limits.tasks_answered_today: %r', e)
        return 0


def item_is_free_to_touch(item_id: int, user_id: int) -> bool:
    """Долг, уже отвеченная задача или чужая/несуществующая — лимит не применяем."""
    try:
        row = _db().session.execute(text("""
            SELECT i.answered_at, i.debt_status FROM daily_task_items i JOIN daily_task_sets st ON st.id = i.daily_set_id
            WHERE i.id = :i AND st.user_id = :u
        """), {'i': item_id, 'u': user_id}).first()
    except Exception:
        _db().session.rollback()
        return True
    if row is None:
        return True
    answered, debt = row[0], (row[1] or '')
    return bool(answered) or debt == 'active'


def task_limit_state(user) -> dict:
    n = free_tasks()
    used = tasks_answered_today(user.id)
    return {'limit': n, 'used': used, 'left': max(0, n - used), 'reached': used >= n,
            'streak_required': streak_required(n)}


def _wants_json() -> bool:
    if request.is_json:
        return True
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept and 'text/html' not in accept


def _limit_response(kind: str, state: dict):
    try:
        from services.funnel import track
        from services.ab import cohort_of
        track('limit_hit', {'kind': kind, 'ab': cohort_of(current_user.id), 'used': state.get('used'),
                            'limit': state.get('limit')})
    except Exception:
        pass
    html = ''
    try:
        html = render_template('partials/limit_reached.html', state=state, kind=kind, upgrade_url=UPGRADE_URL)
    except Exception as e:
        logger.warning('limit_reached partial failed: %r', e)
    if request.method != 'GET' or _wants_json():
        return jsonify({'error': 'limit', 'kind': kind, 'upgrade_url': UPGRADE_URL,
                        'used': state.get('used'), 'limit': state.get('limit'), 'html': html}), 402
    try:
        return render_template('billing/limit.html', state=state, kind=kind, upgrade_url=UPGRADE_URL), 200
    except Exception:
        return html or 'Лимит на сегодня исчерпан', 200


def _wrap(app, endpoint: str, kind: str, item_arg: str = 'item_id'):
    orig = app.view_functions.get(endpoint)
    if orig is None or getattr(orig, '_limits_wrapped', False):
        return

    def wrapper(*a, **kw):
        try:
            if limits_apply(current_user):
                item_id = kw.get(item_arg)
                if kind == 'task':
                    if item_id is None or not item_is_free_to_touch(int(item_id), current_user.id):
                        st = task_limit_state(current_user)
                        if st['reached']:
                            return _limit_response('task', st)
                elif kind == 'ai':
                    from services.subscription import get_subscription_service, PLAN_LIMITS
                    PLAN_LIMITS['free']['ai_explanations_per_day'] = free_ai()
                    ok, _msg = get_subscription_service().can_use_feature(current_user.id, 'ai_explanation')
                    if not ok:
                        usage = get_subscription_service().get_today_usage(current_user.id)
                        return _limit_response('ai', {'limit': free_ai(), 'used': usage.get('ai_explanations_used', 0),
                                                      'left': 0, 'reached': True})
        except Exception as e:  # лимиты никогда не роняют сайт
            logger.warning('soft_limits wrapper error (%s): %r — fail open', endpoint, e)
        resp = orig(*a, **kw)
        if kind == 'ai':
            try:
                if limits_apply(current_user):
                    r = resp[0] if isinstance(resp, tuple) else resp
                    if getattr(r, 'status_code', 200) < 400:
                        from services.subscription import get_subscription_service
                        get_subscription_service().increment_usage(current_user.id, 'ai_explanation')
                        _db().session.commit()
            except Exception as e:
                _db().session.rollback()
                logger.debug('soft_limits ai increment skipped: %r', e)
        return resp

    wrapper.__name__ = getattr(orig, '__name__', 'view')
    wrapper._limits_wrapped = True
    app.view_functions[endpoint] = wrapper


def _late_wrap(app):
    for rule in app.url_map.iter_rules():
        r = str(rule.rule)
        methods = rule.methods or set()
        if r in ('/daily_tasks/<int:item_id>/submit', '/daily_tasks/<int:item_id>/submit_ai') and 'POST' in methods:
            _wrap(app, rule.endpoint, 'task')
        elif r == '/daily_tasks/<int:item_id>' and 'GET' in methods:
            _wrap(app, rule.endpoint, 'task')
        elif r.startswith('/api/tutor') and 'POST' in methods:
            _wrap(app, rule.endpoint, 'ai')


def install(app) -> None:
    if not ENABLED or app.extensions.get('soft_limits_installed'):
        return
    app.extensions['soft_limits_installed'] = True
    try:
        from services.subscription import PLAN_LIMITS
        PLAN_LIMITS['free']['tasks_per_day'] = free_tasks()
        PLAN_LIMITS['free']['ai_explanations_per_day'] = free_ai()
    except Exception as e:
        logger.warning('soft_limits: PLAN_LIMITS update failed: %r', e)
    state = {'done': False}

    @app.before_request
    def _soft_limits_late_wrap():
        if not state['done']:
            state['done'] = True
            try:
                _late_wrap(app)
            except Exception as e:
                logger.warning('soft_limits: wrapping failed: %r', e)

    @app.context_processor
    def _inject_limits():
        try:
            if limits_apply(current_user):
                return {'daily_limit': task_limit_state(current_user)}
        except Exception:
            pass
        return {'daily_limit': None}
    logger.info('SOFT_LIMITS_V1 registered (tasks=%s, ai=%s)', free_tasks(), free_ai())
