# -*- coding: utf-8 -*-
"""
Blueprint: админ-панель отзывов.

Endpoints:
  GET        /admin/reviews                 — список (с фильтром published/draft)
  GET/POST   /admin/reviews/new             — создать отзыв
  GET/POST   /admin/reviews/<id>/edit       — редактировать
  POST       /admin/reviews/<id>/delete     — удалить
  POST       /admin/reviews/<id>/toggle     — publish / unpublish
"""

from __future__ import annotations

import os
import uuid
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, current_app
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from models import db, Review

admin_reviews_bp = Blueprint(
    'admin_reviews', __name__, template_folder='../templates'
)

ALLOWED_AVATAR_EXT = {'png', 'jpg', 'jpeg', 'webp', 'gif'}


# ─── auth ────────────────────────────────────────────────────────────────────
def admin_required(f):
    """user.id==1 ИЛИ email в ADMIN_EMAILS (env)."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        admin_emails = [e.strip() for e in os.environ.get('ADMIN_EMAILS', '').split(',') if e.strip()]
        is_admin = (
            current_user.is_authenticated and (
                current_user.id == 1
                or (getattr(current_user, 'email', None) in admin_emails)
            )
        )
        if not is_admin:
            flash('Доступ только для администраторов', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ─── helpers ────────────────────────────────────────────────────────────────
def _save_avatar(file_storage) -> str | None:
    if not file_storage or not file_storage.filename:
        return None
    fname = secure_filename(file_storage.filename)
    ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
    if ext not in ALLOWED_AVATAR_EXT:
        return None
    new_name = f'rev_{uuid.uuid4().hex[:10]}.{ext}'
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'reviews')
    os.makedirs(upload_dir, exist_ok=True)
    file_storage.save(os.path.join(upload_dir, new_name))
    return f'/static/uploads/reviews/{new_name}'


def _read_form(review: Review) -> None:
    review.name = (request.form.get('name') or '').strip()[:64] or 'Аноним'
    review.role = (request.form.get('role') or '').strip()[:64] or None
    review.grade = (request.form.get('grade') or '').strip()[:16] or None
    review.text = (request.form.get('text') or '').strip()
    try:
        review.rating = max(1, min(5, int(request.form.get('rating', 5))))
    except (TypeError, ValueError):
        review.rating = 5
    try:
        review.sort_order = int(request.form.get('sort_order', 0))
    except (TypeError, ValueError):
        review.sort_order = 0
    review.is_published = bool(request.form.get('is_published'))

    # avatar: либо upload, либо ручной URL
    uploaded = _save_avatar(request.files.get('avatar'))
    manual_url = (request.form.get('avatar_url') or '').strip()
    if uploaded:
        review.avatar_url = uploaded
    elif manual_url:
        review.avatar_url = manual_url[:256]


# ─── list ────────────────────────────────────────────────────────────────────
@admin_reviews_bp.route('/admin/reviews')
@admin_required
def list_reviews():
    status = (request.args.get('status') or 'all').lower()
    q = Review.query
    if status == 'published':
        q = q.filter_by(is_published=True)
    elif status == 'draft':
        q = q.filter_by(is_published=False)
    reviews = q.order_by(Review.sort_order.asc(), Review.created_at.desc()).all()
    return render_template('admin/reviews_list.html', reviews=reviews, status=status)


# ─── create ─────────────────────────────────────────────────────────────────
@admin_reviews_bp.route('/admin/reviews/new', methods=['GET', 'POST'])
@admin_required
def create_review():
    if request.method == 'POST':
        try:
            review = Review()
            _read_form(review)
            db.session.add(review)
            db.session.commit()
            flash('✅ Отзыв создан', 'success')
            return redirect(url_for('admin_reviews.list_reviews'))
        except Exception as exc:
            db.session.rollback()
            flash(f'❌ Ошибка: {exc}', 'error')
    return render_template('admin/reviews_form.html', review=None)


# ─── edit ───────────────────────────────────────────────────────────────────
@admin_reviews_bp.route('/admin/reviews/<int:rid>/edit', methods=['GET', 'POST'])
@admin_required
def edit_review(rid: int):
    review = Review.query.get_or_404(rid)
    if request.method == 'POST':
        try:
            _read_form(review)
            db.session.commit()
            flash('✅ Сохранено', 'success')
            return redirect(url_for('admin_reviews.list_reviews'))
        except Exception as exc:
            db.session.rollback()
            flash(f'❌ Ошибка: {exc}', 'error')
    return render_template('admin/reviews_form.html', review=review)


# ─── delete ─────────────────────────────────────────────────────────────────
@admin_reviews_bp.route('/admin/reviews/<int:rid>/delete', methods=['POST'])
@admin_required
def delete_review(rid: int):
    review = Review.query.get_or_404(rid)
    db.session.delete(review)
    db.session.commit()
    flash('🗑 Удалено', 'success')
    return redirect(url_for('admin_reviews.list_reviews'))


# ─── toggle publish ─────────────────────────────────────────────────────────
@admin_reviews_bp.route('/admin/reviews/<int:rid>/toggle', methods=['POST'])
@admin_required
def toggle_review(rid: int):
    review = Review.query.get_or_404(rid)
    review.is_published = not review.is_published
    db.session.commit()
    flash('🔁 Статус обновлён', 'success')
    return redirect(url_for('admin_reviews.list_reviews'))
