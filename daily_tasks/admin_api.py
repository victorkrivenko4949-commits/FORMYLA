# -*- coding: utf-8 -*-
"""daily_tasks/admin_api.py — админ-API: задачи дня конкретного ученика из банка.

Маршруты (под префиксом daily_tasks_bp, т.е. /daily_tasks/...):
    GET /daily_tasks/admin/api/find_user?q=<имя|email|ник>
    GET /daily_tasks/admin/api/user/<user_id>?date=YYYY-MM-DD[&issue=1]

Доступ: залогиненный админ (current_user.is_admin) ЛИБО заголовок
X-Admin-Token (или ?token=), равный переменной окружения ADMIN_API_TOKEN
(если она задана; пустая переменная = токен-доступ выключен).

Ничего не генерирует и не меняет: читает user_subtopic_assignments
(через curator_plan_service), уровень mu (через bank_daily.user_level),
bank_issues и daily_task_bank. С issue=1 — вызывает
services.bank_daily.build_daily_set, т.е. выдаёт набор на дату ровно так,
как это делает страница /daily_tasks при первом открытии.
"""
from __future__ import annotations

import hmac
import logging
import os
from datetime import date, datetime, timedelta

from flask import jsonify, request
from flask_login import current_user

logger = logging.getLogger(__name__)


def _msk_today() -> date:
    return (datetime.utcnow() + timedelta(hours=3)).date()


def _token_ok() -> bool:
    token = (os.environ.get('ADMIN_API_TOKEN') or '').strip()
    if not token:
        return False
    sent = (request.headers.get('X-Admin-Token') or request.args.get('token') or '').strip()
    return bool(sent) and hmac.compare_digest(sent, token)


def _is_admin() -> bool:
    try:
        if getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'is_admin', False) is True:
            return True
    except Exception:
        pass
    return _token_ok()


def _parse_date(raw):
    if not raw:
        return _msk_today()
    return date.fromisoformat(str(raw)[:10])


def _jsonable(d):
    out = {}
    for k, v in dict(d or {}).items():
        out[str(k)] = v if isinstance(v, (str, int, float, bool, type(None), list, dict)) else str(v)
    return out


def _task_dict(t, issue=None):
    d = {
        'task_id': t.id,
        'subtopic': t.subtopic,
        'section': t.section,
        'level': t.level,
        'position': getattr(t, 'position', None),
        'statement': t.statement,
        'answer': t.answer,
        'solution': t.solution,
        'needs_figure': bool(getattr(t, 'needs_figure', False)),
        'svg_path': getattr(t, 'svg_path', None),
    }
    if issue is not None:
        d.update({
            'issued_date': issue.issued_date.isoformat() if getattr(issue, 'issued_date', None) else None,
            'user_answer': getattr(issue, 'user_answer', None),
            'is_correct': getattr(issue, 'is_correct', None),
            'answered_at': issue.answered_at.isoformat() if getattr(issue, 'answered_at', None) else None,
        })
    return d


def attach(bp):
    """Повесить маршруты на daily_tasks_bp (вызывается из daily_tasks/__init__)."""

    @bp.route('/admin/api/find_user')
    def admin_api_find_user():
        if not _is_admin():
            return jsonify({'error': 'forbidden'}), 403
        from sqlalchemy import or_
        from models import User
        q = (request.args.get('q') or '').strip()
        if len(q) < 2:
            return jsonify({'error': 'q_too_short'}), 400
        like = f'%{q}%'
        conds = []
        for col in ('name', 'nickname', 'email'):
            attr = getattr(User, col, None)
            if attr is not None:
                conds.append(attr.ilike(like))
        users = User.query.filter(or_(*conds)).limit(20).all() if conds else []
        return jsonify({'q': q, 'users': [{
            'id': u.id,
            'name': getattr(u, 'name', None),
            'nickname': getattr(u, 'nickname', None),
            'email': getattr(u, 'email', None),
            'created_at': u.created_at.isoformat() if getattr(u, 'created_at', None) else None,
        } for u in users]})

    @bp.route('/admin/api/user/<int:user_id>')
    def admin_api_user_daily(user_id):
        if not _is_admin():
            return jsonify({'error': 'forbidden'}), 403
        from models import db, User, DailyTaskBank, BankIssue
        from services import bank_daily

        user = db.session.get(User, user_id)
        if user is None:
            return jsonify({'error': 'not_found'}), 404
        try:
            target = _parse_date(request.args.get('date'))
        except ValueError:
            return jsonify({'error': 'bad_date'}), 400

        try:
            from services.curator_plan_service import get_active_subtopics
            assignments, plan_status = get_active_subtopics(user_id)
            plan_subtopics = [str(a.subtopic) for a in (assignments or [])]
        except Exception as e:
            logger.warning('admin_api_user_daily: get_active_subtopics: %r', e)
            plan_status, plan_subtopics = {'error': str(e)}, []

        levels = {}
        for s in plan_subtopics:
            try:
                levels[s] = bank_daily.user_level(user_id, s)
            except Exception:
                levels[s] = None

        issues = (BankIssue.query
                  .filter_by(user_id=user_id, issued_date=target)
                  .order_by(BankIssue.id.asc()).all())
        built = None
        if not issues and request.args.get('issue') == '1':
            built = bank_daily.build_daily_set(user_id, target)
            issues = (BankIssue.query
                      .filter_by(user_id=user_id, issued_date=target)
                      .order_by(BankIssue.id.asc()).all())

        task_ids = [int(i.task_id) for i in issues]
        tasks = ({t.id: t for t in DailyTaskBank.query.filter(DailyTaskBank.id.in_(task_ids)).all()}
                 if task_ids else {})
        items = [_task_dict(tasks[i.task_id], i) for i in issues if i.task_id in tasks]

        grade = None
        try:
            from models_curator import CuratorState
            cs = CuratorState.query.filter_by(user_id=user_id).first()
            grade = getattr(cs, 'grade', None) if cs is not None else None
        except Exception:
            pass
        if grade is None:
            grade = getattr(user, 'class_level', None) or getattr(user, 'grade', None)

        return jsonify({
            'user': {'id': user.id, 'name': getattr(user, 'name', None),
                     'nickname': getattr(user, 'nickname', None),
                     'email': getattr(user, 'email', None), 'grade': grade},
            'date': target.isoformat(),
            'plan': {'subtopics': plan_subtopics, 'status': _jsonable(plan_status)},
            'levels_by_subtopic': levels,
            'today_subtopics': sorted({str(i.subtopic) for i in issues if i.subtopic}),
            'issued': len(items),
            'answered': sum(1 for i in issues if getattr(i, 'answered_at', None) is not None
                            or getattr(i, 'user_answer', None) is not None),
            'correct': sum(1 for i in issues if bool(getattr(i, 'is_correct', False))),
            'built_now': None if built is None else _jsonable({k: v for k, v in built.items() if k != 'items'}),
            'tasks': items,
        })

    logger.info('daily_tasks admin_api attached')
