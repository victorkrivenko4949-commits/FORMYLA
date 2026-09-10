# -*- coding: utf-8 -*-
"""
Blueprint: Подготовка к олимпиадам (olympiad_prep)

Endpoints:
  GET /olympiad-prep              — редирект на календарь (каталог упразднён)
  GET /olympiad-prep/calendar     — календарь олимпиад (заглушка)
  GET /olympiad-prep/<slug>       — страница конкретной олимпиады
"""

from flask import Blueprint, render_template, abort, redirect, url_for
from flask_login import current_user

from models import OlympiadPrep, PrepPlan

olympiad_prep_bp = Blueprint(
    'olympiad_prep',
    __name__,
    template_folder='../templates',
)


@olympiad_prep_bp.route('/olympiad-prep')
def index():
    """Страница-каталог упразднена: отправляем в календарь олимпиад."""
    return redirect(url_for('olympiad_prep.calendar'), code=302)


@olympiad_prep_bp.route('/olympiad-prep/calendar')
def calendar():
    """Календарь олимпиад России — расписание этапов."""
    olympiads = (
        OlympiadPrep.query
        .filter_by(is_active=True)
        .order_by(OlympiadPrep.sort_order)
        .all()
    )
    return render_template('olympiad_prep/calendar.html', olympiads=olympiads)


@olympiad_prep_bp.route('/olympiad-prep/<slug>')
def detail(slug):
    """Страница конкретной олимпиады.

    If the user is authenticated, also passes their existing PrepPlan
    for this olympiad (if any) so the template can show a live button
    instead of the "coming soon" stub.
    """
    olympiad = OlympiadPrep.query.filter_by(slug=slug, is_active=True).first()
    if not olympiad:
        abort(404)

    # Check if the logged-in user already has a plan for this olympiad
    user_plan = None
    if current_user.is_authenticated:
        user_plan = (
            PrepPlan.query
            .filter_by(user_id=current_user.id, olympiad_id=olympiad.id)
            .filter(PrepPlan.status.in_(['active', 'paused']))
            .first()
        )

    return render_template(
        'olympiad_prep/detail.html',
        olympiad=olympiad,
        user_plan=user_plan,
    )
