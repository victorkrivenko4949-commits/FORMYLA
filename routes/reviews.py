# -*- coding: utf-8 -*-
"""
Blueprint: публичная форма отзыва.

GET  /reviews/new   — форма (любой посетитель, без авторизации).
POST /reviews/new   — сохранение в БД с `is_published=False`. Админ модерирует
                       и публикует через /admin/reviews.

Лёгкая защита:
- honeypot-поле `website` (если заполнено — бот, тихий 200);
- in-memory rate-limit: не более 3 отзывов с одного session_id / IP / 60 минут;
- лимиты длины полей.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g
)
from flask_login import current_user

from models import db, Review

logger = logging.getLogger(__name__)

reviews_bp = Blueprint('reviews', __name__, template_folder='../templates')

# ─── rate-limit (in-memory, per-process) ─────────────────────────────────────
_RL_WINDOW = 60 * 60      # 60 минут
_RL_MAX = 3               # не более 3 успешных отправок
_RL_STORE: "defaultdict[str, deque[float]]" = defaultdict(deque)


def _rl_key() -> str:
    sid = getattr(g, 'analytics_session_id', None) or ''
    ip = (request.headers.get('X-Forwarded-For') or request.remote_addr or '').split(',')[0].strip()
    return f'{sid}|{ip}'


def _rl_check_and_bump() -> bool:
    """True — если можно отправить; False — лимит."""
    now = time.time()
    dq = _RL_STORE[_rl_key()]
    while dq and (now - dq[0]) > _RL_WINDOW:
        dq.popleft()
    if len(dq) >= _RL_MAX:
        return False
    dq.append(now)
    return True


# ─── allowed roles (selectable in form) ──────────────────────────────────────
ALLOWED_ROLES = ['ученик', 'ученица', 'родитель', 'преподаватель', 'другое']


def _clean(val, max_len: int) -> str:
    s = (val or '').strip()
    if not s:
        return ''
    return s[:max_len]


@reviews_bp.route('/reviews/new', methods=['GET', 'POST'])
def submit_review():
    if request.method == 'POST':
        # honeypot — невидимое поле, заполняется только ботами.
        if (request.form.get('website') or '').strip():
            logger.info('[reviews] honeypot triggered, silently 200')
            return redirect(url_for('reviews.thanks'))

        if not _rl_check_and_bump():
            flash('Слишком часто. Попробуйте позже.', 'error')
            return render_template(
                'reviews_new.html',
                form=request.form,
                allowed_roles=ALLOWED_ROLES,
            ), 429

        name = _clean(request.form.get('name'), 64) or 'Аноним'
        role = _clean(request.form.get('role'), 64) or None
        if role and role not in ALLOWED_ROLES:
            role = 'другое'
        grade = _clean(request.form.get('grade'), 16) or None
        text = _clean(request.form.get('text'), 2000)

        try:
            rating = int(request.form.get('rating', 5))
        except (TypeError, ValueError):
            rating = 5
        rating = max(1, min(5, rating))

        if len(text) < 20:
            flash('Расскажите подробнее — минимум 20 символов.', 'error')
            return render_template(
                'reviews_new.html',
                form=request.form,
                allowed_roles=ALLOWED_ROLES,
            ), 400

        try:
            review = Review(
                name=name,
                role=role,
                grade=grade,
                text=text,
                rating=rating,
                avatar_url=None,
                is_published=False,    # ждёт модерации
                sort_order=0,
            )
            db.session.add(review)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.warning('[reviews] DB save failed: %s', exc)
            flash('Не удалось сохранить отзыв. Попробуйте позже.', 'error')
            return render_template(
                'reviews_new.html',
                form=request.form,
                allowed_roles=ALLOWED_ROLES,
            ), 500

        # Аналитика — best-effort.
        try:
            from routes.track import log_event
            log_event('review_submitted', meta={
                'review_id': review.id,
                'role': role,
                'rating': rating,
                'len': len(text),
                'authed': bool(current_user.is_authenticated),
            })
        except Exception:
            pass

        return redirect(url_for('reviews.thanks'))

    # GET — пустая форма.
    return render_template(
        'reviews_new.html',
        form={},
        allowed_roles=ALLOWED_ROLES,
    )


@reviews_bp.route('/reviews/thanks')
def thanks():
    return render_template(
        'reviews_new.html',
        form={},
        allowed_roles=ALLOWED_ROLES,
        submitted=True,
    )
