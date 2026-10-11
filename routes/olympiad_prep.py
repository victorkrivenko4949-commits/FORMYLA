# -*- coding: utf-8 -*-
"""
Blueprint: Подготовка к олимпиадам (olympiad_prep)

Endpoints:
  GET /olympiad-prep              — редирект на календарь (каталог упразднён)
  GET /olympiad-prep/calendar     — календарь олимпиад (точные даты, регистрация, инструкции)
  GET /olympiad-prep/<slug>       — страница конкретной олимпиады
"""

from datetime import date

from flask import Blueprint, render_template, abort, redirect, url_for
from flask_login import current_user

from models import OlympiadPrep, PrepPlan
from olympiad_calendar_data import build_calendar, SEASON

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
    """Календарь олимпиад России — точные даты, статус регистрации, инструкции.

    Статические данные сезона (olympiad_calendar_data.OLYMPIADS) объединяются
    с записями OlympiadPrep из БД (цвет, slug, ссылка на страницу олимпиады).
    Если БД недоступна, календарь всё равно рендерится из статических данных.
    """
    try:
        olympiads = (
            OlympiadPrep.query
            .filter_by(is_active=True)
            .order_by(OlympiadPrep.sort_order)
            .all()
        )
    except Exception:
        olympiads = []

    cards, summary, today = build_calendar(olympiads, date.today())
    return render_template(
        'olympiad_prep/calendar.html',
        cards=cards,
        summary=summary,
        today=today,
        season=SEASON,
        olympiads=olympiads,
    )


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

    # Старые планы подготовки удалены (2026-09-14) — на странице олимпиады
    # больше не показываем их. user_plan оставляем None для шаблона.
    return render_template(
        'olympiad_prep/detail.html',
        olympiad=olympiad,
        user_plan=None,
    )
