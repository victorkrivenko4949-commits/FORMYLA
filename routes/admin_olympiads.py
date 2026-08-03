# -*- coding: utf-8 -*-
"""
Blueprint: Админ-панель олимпиад (CRUD)

Endpoints:
  GET        /admin/olympiads              — список олимпиад
  GET/POST   /admin/olympiads/new          — создать олимпиаду
  GET/POST   /admin/olympiads/<id>/edit    — редактировать
  POST       /admin/olympiads/<id>/delete  — удалить
"""

import json
from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user, login_required

from models import db, OlympiadPrep

admin_olympiads_bp = Blueprint(
    'admin_olympiads',
    __name__,
    template_folder='../templates',
)


def admin_required(f):
    """Простая защита: только авторизованные пользователи.
    В будущем можно добавить проверку роли / email."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ─── LIST ─────────────────────────────────────────────────────────────────────

@admin_olympiads_bp.route('/admin/olympiads')
@admin_required
def list_olympiads():
    olympiads = OlympiadPrep.query.order_by(OlympiadPrep.sort_order).all()
    return render_template('admin/olympiads_list.html', olympiads=olympiads)


# ─── CREATE ───────────────────────────────────────────────────────────────────

@admin_olympiads_bp.route('/admin/olympiads/new', methods=['GET', 'POST'])
@admin_required
def create_olympiad():
    if request.method == 'POST':
        try:
            grades_raw = request.form.get('grades', '[]')
            stages_raw = request.form.get('stages', '[]')
            # Accept comma-separated or JSON
            grades = _parse_list(grades_raw, as_int=True)
            stages = _parse_list(stages_raw, as_int=False)

            olympiad = OlympiadPrep(
                slug=request.form['slug'].strip(),
                name=request.form['name'].strip(),
                short_name=request.form['short_name'].strip(),
                description=request.form.get('description', '').strip(),
                grades=json.dumps(grades, ensure_ascii=False),
                stages=json.dumps(stages, ensure_ascii=False),
                official_url=request.form.get('official_url', '').strip(),
                logo_path=request.form.get('logo_path', '').strip(),
                color_hex=request.form.get('color_hex', '#22d3a6').strip(),
                sort_order=int(request.form.get('sort_order', 0)),
                is_active='is_active' in request.form,
            )
            db.session.add(olympiad)
            db.session.commit()
            flash('[OK] Олимпиада создана', 'success')
            return redirect(url_for('admin_olympiads.list_olympiads'))
        except Exception as e:
            db.session.rollback()
            flash(f'[ERROR] Ошибка: {e}', 'error')

    return render_template('admin/olympiad_form.html', olympiad=None)


# ─── EDIT ─────────────────────────────────────────────────────────────────────

@admin_olympiads_bp.route('/admin/olympiads/<int:oid>/edit', methods=['GET', 'POST'])
@admin_required
def edit_olympiad(oid):
    olympiad = OlympiadPrep.query.get_or_404(oid)

    if request.method == 'POST':
        try:
            grades = _parse_list(request.form.get('grades', '[]'), as_int=True)
            stages = _parse_list(request.form.get('stages', '[]'), as_int=False)

            olympiad.slug = request.form['slug'].strip()
            olympiad.name = request.form['name'].strip()
            olympiad.short_name = request.form['short_name'].strip()
            olympiad.description = request.form.get('description', '').strip()
            olympiad.grades = json.dumps(grades, ensure_ascii=False)
            olympiad.stages = json.dumps(stages, ensure_ascii=False)
            olympiad.official_url = request.form.get('official_url', '').strip()
            olympiad.logo_path = request.form.get('logo_path', '').strip()
            olympiad.color_hex = request.form.get('color_hex', '#22d3a6').strip()
            olympiad.sort_order = int(request.form.get('sort_order', 0))
            olympiad.is_active = 'is_active' in request.form

            db.session.commit()
            flash('[OK] Олимпиада обновлена', 'success')
            return redirect(url_for('admin_olympiads.list_olympiads'))
        except Exception as e:
            db.session.rollback()
            flash(f'[ERROR] Ошибка: {e}', 'error')

    return render_template('admin/olympiad_form.html', olympiad=olympiad)


# ─── DELETE ───────────────────────────────────────────────────────────────────

@admin_olympiads_bp.route('/admin/olympiads/<int:oid>/delete', methods=['POST'])
@admin_required
def delete_olympiad(oid):
    olympiad = OlympiadPrep.query.get_or_404(oid)
    db.session.delete(olympiad)
    db.session.commit()
    flash(f'️ Олимпиада «{olympiad.name}» удалена', 'success')
    return redirect(url_for('admin_olympiads.list_olympiads'))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_list(raw: str, as_int: bool = False) -> list:
    """Parse comma-separated or JSON list string."""
    raw = raw.strip()
    if not raw:
        return []
    # Try JSON first
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return [int(x) for x in result] if as_int else [str(x).strip() for x in result]
    except (json.JSONDecodeError, ValueError):
        pass
    # Fallback: comma-separated
    parts = [p.strip() for p in raw.split(',') if p.strip()]
    if as_int:
        return [int(p) for p in parts]
    return parts
