# -*- coding: utf-8 -*-
"""Blueprint: тренажёр /grade-5 и /grade-6.

Маршруты:
    GET /grade-5                    обзор курса 5 класса (5 доменов)
    GET /grade-6                    обзор курса 6 класса (5 доменов)
    GET /grade-5/<domain>           список задач домена с фильтром по level
    GET /grade-6/<domain>           то же для 6 класса
    GET /grade-task/<task_id>       одна задача (карточка)
"""

from __future__ import annotations

from flask import Blueprint, abort, render_template, request
from sqlalchemy import asc

from models import db
from models_grade import GradeTask, GRADE_DOMAINS, DOMAIN_LABELS


grade_bp = Blueprint('grade', __name__)


def _validate_grade(grade: int):
    if grade not in (5, 6):
        abort(404)


def _domain_stats(grade: int):
    """Вернуть [(domain, label, count, level_counts), ...] для overview."""
    rows = (
        db.session.query(GradeTask.domain, GradeTask.level)
        .filter(GradeTask.grade == grade)
        .all()
    )
    by_domain = {}
    for d, lvl in rows:
        item = by_domain.setdefault(d, {'count': 0, 'levels': {}})
        item['count'] += 1
        if lvl is not None:
            item['levels'][lvl] = item['levels'].get(lvl, 0) + 1
    result = []
    for d in GRADE_DOMAINS.get(grade, ()):
        info = by_domain.get(d, {'count': 0, 'levels': {}})
        result.append({
            'domain': d,
            'label': DOMAIN_LABELS.get(d, d),
            'count': info['count'],
            'levels': info['levels'],
        })
    return result


# ─── Overview ─────────────────────────────────────────────────────────────────

@grade_bp.route('/grade-5', endpoint='overview_5')
def overview_5():
    return _render_overview(5)


@grade_bp.route('/grade-6', endpoint='overview_6')
def overview_6():
    return _render_overview(6)


def _render_overview(grade: int):
    _validate_grade(grade)
    stats = _domain_stats(grade)
    total = sum(s['count'] for s in stats)
    return render_template(
        'grade/overview.html',
        grade=grade,
        stats=stats,
        total=total,
    )


# ─── Domain list ──────────────────────────────────────────────────────────────

@grade_bp.route('/grade-5/<string:domain>', endpoint='domain_5')
def domain_5(domain):
    return _render_domain(5, domain)


@grade_bp.route('/grade-6/<string:domain>', endpoint='domain_6')
def domain_6(domain):
    return _render_domain(6, domain)


def _render_domain(grade: int, domain: str):
    _validate_grade(grade)
    if domain not in GRADE_DOMAINS.get(grade, ()):
        abort(404)

    level = request.args.get('level', type=int)
    if level is not None and not (1 <= level <= 7):
        level = None

    q = GradeTask.query.filter_by(grade=grade, domain=domain)
    if level is not None:
        q = q.filter(GradeTask.level == level)
    q = q.order_by(
        asc(GradeTask.level.is_(None)),  # nulls last
        asc(GradeTask.level),
        asc(GradeTask.source_id),
    )
    tasks = q.all()

    available_levels = sorted(
        {t.level for t in GradeTask.query.filter_by(grade=grade, domain=domain).all()
         if t.level is not None}
    )

    return render_template(
        'grade/domain.html',
        grade=grade,
        domain=domain,
        domain_label=DOMAIN_LABELS.get(domain, domain),
        tasks=tasks,
        level=level,
        available_levels=available_levels,
    )


# ─── Task detail ──────────────────────────────────────────────────────────────

@grade_bp.route('/grade-task/<int:task_id>', endpoint='task')
def task_page(task_id):
    task = db.session.get(GradeTask, task_id)
    if task is None:
        abort(404)
    return render_template('grade/task.html', task=task,
                           domain_label=DOMAIN_LABELS.get(task.domain, task.domain))
