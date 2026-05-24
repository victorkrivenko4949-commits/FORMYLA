# -*- coding: utf-8 -*-
"""Blueprint: дашборд аналитики /admin/analytics."""
from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user, login_required
from sqlalchemy import func, distinct

from models import db, Event, User

logger = logging.getLogger(__name__)

admin_analytics_bp = Blueprint(
    'admin_analytics', __name__, template_folder='../templates'
)


def _is_admin() -> bool:
    if not current_user.is_authenticated:
        return False
    admin_emails = [
        e.strip() for e in os.environ.get('ADMIN_EMAILS', '').split(',') if e.strip()
    ]
    return (
        current_user.id == 1
        or (getattr(current_user, 'email', None) in admin_emails)
    )


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not _is_admin():
            return jsonify({'error': 'forbidden'}), 403
        return f(*args, **kwargs)
    return decorated


def _range_to_dt(rng: str):
    rng = (rng or '7d').lower()
    if rng == 'all':
        return None
    days = 7
    if rng.endswith('d'):
        try:
            days = int(rng[:-1])
        except ValueError:
            days = 7
    return datetime.utcnow() - timedelta(days=days)


def _date_str(dt) -> str:
    if not dt:
        return ''
    if hasattr(dt, 'strftime'):
        return dt.strftime('%Y-%m-%d')
    return str(dt)[:10]


@admin_analytics_bp.route('/admin/analytics')
@admin_required
def dashboard():
    return render_template('admin_analytics.html')


@admin_analytics_bp.route('/admin/analytics/data')
@admin_required
def data():
    rng = request.args.get('range', '7d')
    since = _range_to_dt(rng)
    return jsonify({
        'range': rng,
        'funnel': _funnel(since),
        'sources': _sources(since),
        'ab_test': _ab_test(since),
        'dau_wau_mau': _dau_wau_mau(since),
        'retention': _retention(since),
        'activation': _activation(since),
        'ai_usage': _ai_usage(since),
        'top_problems': _top_problems(since),
    })


FUNNEL_STEPS = [
    'landing_view', 'cta_click', 'mock_start', 'mock_complete',
    'signup', 'daily_done_d1',
]


def _funnel(since):
    q = db.session.query(Event.event, func.count(Event.id))
    if since is not None:
        q = q.filter(Event.created_at >= since)
    q = q.filter(Event.event.in_(FUNNEL_STEPS))
    counts = dict(q.group_by(Event.event).all())
    return [{'step': s, 'count': int(counts.get(s, 0))} for s in FUNNEL_STEPS]


def _sources(since):
    q = db.session.query(
        func.date(Event.created_at).label('d'),
        Event.utm_source,
        func.count(distinct(func.coalesce(Event.user_id, Event.session_id))),
    )
    if since is not None:
        q = q.filter(Event.created_at >= since)
    q = q.filter(Event.event == 'landing_view')
    rows = q.group_by('d', Event.utm_source).order_by('d').all()
    return [
        {'date': _date_str(r[0]), 'utm_source': r[1] or '(direct)', 'users': int(r[2])}
        for r in rows
    ]


def _ab_test(since):
    q_views = db.session.query(Event.utm_content, func.count(Event.id)).filter(
        Event.event == 'landing_view'
    )
    q_signups = db.session.query(Event.utm_content, func.count(Event.id)).filter(
        Event.event == 'signup'
    )
    if since is not None:
        q_views = q_views.filter(Event.created_at >= since)
        q_signups = q_signups.filter(Event.created_at >= since)
    views = dict(q_views.group_by(Event.utm_content).all())
    signups = dict(q_signups.group_by(Event.utm_content).all())
    keys = sorted({*views.keys(), *signups.keys()}, key=lambda x: (x is None, x or ''))
    result = []
    for k in keys:
        label = k if k else '(none)'
        v = int(views.get(k, 0))
        s = int(signups.get(k, 0))
        cr = round(s / v, 4) if v > 0 else 0.0
        result.append({'variant': label, 'views': v, 'signups': s, 'cr': cr})
    return result


def _dau_wau_mau(since):
    end = datetime.utcnow().date()
    if since is None:
        start = end - timedelta(days=30)
    else:
        start = since.date()
    if (end - start).days > 90:
        start = end - timedelta(days=90)

    result = []
    d = start
    while d <= end:
        d0 = datetime.combine(d, datetime.min.time())
        d1 = d0 + timedelta(days=1)
        dau = db.session.query(
            func.count(distinct(func.coalesce(Event.user_id, Event.session_id)))
        ).filter(Event.created_at >= d0, Event.created_at < d1).scalar() or 0
        wau = db.session.query(
            func.count(distinct(func.coalesce(Event.user_id, Event.session_id)))
        ).filter(
            Event.created_at >= d0 - timedelta(days=6), Event.created_at < d1
        ).scalar() or 0
        mau = db.session.query(
            func.count(distinct(func.coalesce(Event.user_id, Event.session_id)))
        ).filter(
            Event.created_at >= d0 - timedelta(days=29), Event.created_at < d1
        ).scalar() or 0
        result.append({
            'date': d.isoformat(),
            'dau': int(dau),
            'wau': int(wau),
            'mau': int(mau),
        })
        d += timedelta(days=1)
    return result


def _retention(since):
    q = (
        db.session.query(func.date(Event.created_at), Event.user_id)
        .filter(Event.event == 'signup', Event.user_id.isnot(None))
    )
    if since is not None:
        q = q.filter(Event.created_at >= since)
    rows = q.all()

    cohorts = {}
    for d, uid in rows:
        key = _date_str(d)
        cohorts.setdefault(key, set()).add(uid)

    result = []
    for cohort_date in sorted(cohorts.keys())[-8:]:
        users = cohorts[cohort_date]
        if not users:
            continue
        try:
            base = datetime.strptime(cohort_date, '%Y-%m-%d')
        except ValueError:
            continue
        size = len(users)
        item = {'cohort': cohort_date}
        for label, day_n in [('d1', 1), ('d3', 3), ('d7', 7), ('d14', 14)]:
            start_dt = base + timedelta(days=day_n)
            end_dt = start_dt + timedelta(days=1)
            active = db.session.query(
                func.count(distinct(Event.user_id))
            ).filter(
                Event.user_id.in_(list(users)),
                Event.created_at >= start_dt,
                Event.created_at < end_dt,
            ).scalar() or 0
            item[label] = round(active / size, 4) if size > 0 else 0.0
        result.append(item)
    return result


def _activation(since):
    """Activation rate = signup → daily_done_d1 within 48h, по дням."""
    end = datetime.utcnow().date()
    start = (since.date() if since else end - timedelta(days=30))
    if (end - start).days > 60:
        start = end - timedelta(days=60)

    result = []
    d = start
    while d <= end:
        d0 = datetime.combine(d, datetime.min.time())
        d1 = d0 + timedelta(days=1)
        signups = db.session.query(Event.user_id).filter(
            Event.event == 'signup',
            Event.user_id.isnot(None),
            Event.created_at >= d0,
            Event.created_at < d1,
        ).all()
        uids = [u[0] for u in signups]
        rate = 0.0
        if uids:
            activated = db.session.query(
                func.count(distinct(Event.user_id))
            ).filter(
                Event.user_id.in_(uids),
                Event.event == 'daily_done_d1',
                Event.created_at >= d0,
                Event.created_at < d0 + timedelta(days=2),
            ).scalar() or 0
            rate = round(activated / len(uids), 4)
        result.append({'date': d.isoformat(), 'rate': rate})
        d += timedelta(days=1)
    return result


def _ai_usage(since):
    """AI requests + cost — пишем в Event(event='ai_request', meta={cost_rub:..})."""
    q = db.session.query(
        func.date(Event.created_at).label('d'),
        func.count(Event.id),
    ).filter(Event.event == 'ai_request')
    if since is not None:
        q = q.filter(Event.created_at >= since)
    rows = q.group_by('d').order_by('d').all()

    # Cost: суммируем meta.cost_rub отдельным запросом (порционно).
    # На SQLite JSON_EACH не везде поддерживается → считаем в Python.
    cost_by_day = {}
    cq = db.session.query(Event.created_at, Event.meta).filter(
        Event.event == 'ai_request'
    )
    if since is not None:
        cq = cq.filter(Event.created_at >= since)
    for created, meta in cq.all():
        if not meta:
            continue
        try:
            v = float((meta or {}).get('cost_rub') or 0)
        except (TypeError, ValueError):
            v = 0.0
        key = _date_str(created)
        cost_by_day[key] = cost_by_day.get(key, 0.0) + v

    return [
        {
            'date': _date_str(r[0]),
            'requests': int(r[1]),
            'cost_rub': round(cost_by_day.get(_date_str(r[0]), 0.0), 2),
        }
        for r in rows
    ]


def _top_problems(since):
    """Топ задач по числу попыток (по событиям task_attempt / problem_attempt)."""
    q = db.session.query(
        Event.meta,
        func.count(Event.id),
    ).filter(Event.event.in_(['task_attempt', 'problem_attempt']))
    if since is not None:
        q = q.filter(Event.created_at >= since)
    rows = q.group_by(Event.meta).all()

    # Группируем по problem_id вручную.
    agg = {}
    for meta, cnt in rows:
        if not meta:
            continue
        pid = meta.get('problem_id') if isinstance(meta, dict) else None
        if pid is None:
            continue
        topic = meta.get('topic', '') if isinstance(meta, dict) else ''
        correct = 1 if (isinstance(meta, dict) and meta.get('correct')) else 0
        cur = agg.setdefault(pid, {
            'problem_id': pid, 'topic': topic,
            'attempts': 0, 'correct': 0,
        })
        cur['attempts'] += int(cnt)
        cur['correct'] += int(correct) * int(cnt)

    items = []
    for v in agg.values():
        cr = round(v['correct'] / v['attempts'], 4) if v['attempts'] > 0 else 0.0
        items.append({
            'problem_id': v['problem_id'],
            'topic': v['topic'],
            'attempts': v['attempts'],
            'correct_rate': cr,
        })
    items.sort(key=lambda x: x['attempts'], reverse=True)
    return items[:15]
