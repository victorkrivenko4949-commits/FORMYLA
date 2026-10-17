# -*- coding: utf-8 -*-
"""PARENT_OFFER_V1 (18.10.2026) — ссылка «Отправить родителю» с экрана лимита.

  POST /parent/offer-link          → {ok, url, token}: токен itsdangerous на 7 дней (PARENT_OFFER_DAYS)
  GET  /parent/offer/<token>       → страница для родителя: что ребёнок делает, что даёт Premium,
                                     кнопка на /subscribe?from=parent_offer (нужен вход/регистрация родителя)
События: parent_link_created, parent_offer_view.
Откат: PARENT_OFFER_ENABLED=0.
"""
from __future__ import annotations

import logging
import os

from flask import Blueprint, abort, jsonify, render_template, request, url_for
from flask_login import current_user, login_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

parent_offer_bp = Blueprint('parent_offer', __name__)
ENABLED = os.environ.get('PARENT_OFFER_ENABLED', '1') != '0'
SALT = 'parent-offer-v1'


def _days() -> int:
    try:
        return max(1, int(os.environ.get('PARENT_OFFER_DAYS', '7') or 7))
    except ValueError:
        return 7


def _serializer():
    from flask import current_app
    return URLSafeTimedSerializer(current_app.secret_key, salt=SALT)


def make_token(user_id: int) -> str:
    return _serializer().dumps({'u': int(user_id)})


def read_token(token: str):
    try:
        return _serializer().loads(token, max_age=_days() * 86400)
    except (BadSignature, SignatureExpired):
        return None


def _track(name, props=None, user_id=None):
    try:
        from services.funnel import track
        track(name, props or {}, user_id=user_id)
    except Exception:
        pass


@parent_offer_bp.route('/parent/offer-link', methods=['POST'])
@login_required
def offer_link():
    token = make_token(current_user.id)
    url = url_for('parent_offer.offer_page', token=token, _external=True)
    _track('parent_link_created', {'from': (request.get_json(silent=True) or {}).get('from')})
    name = getattr(current_user, 'name', None) or getattr(current_user, 'nickname', None) or 'ребёнок'
    text = (f'{name} занимается олимпиадной математикой на FORMYLA и сегодня решил(а) все бесплатные задачи. '
            f'Посмотрите, что даёт Premium: {url}')
    return jsonify(ok=True, url=url, token=token, share_text=text,
                   tg=f'https://t.me/share/url?url={url}', wa=f'https://wa.me/?text={text}')


@parent_offer_bp.route('/parent/offer/<token>')
def offer_page(token):
    data = read_token(token)
    if not data:
        abort(404)
    child = None
    try:
        from models import User
        child = User.query.get(int(data['u']))
    except Exception:
        child = None
    stats = {}
    try:
        from sqlalchemy import text as _t
        from models import db
        row = db.session.execute(_t("""SELECT COUNT(*), COALESCE(SUM(CASE WHEN i.is_correct THEN 1 ELSE 0 END),0)
                                       FROM daily_task_items i JOIN daily_task_sets s ON s.id=i.daily_set_id
                                       WHERE s.user_id=:u AND i.answered_at IS NOT NULL"""), {'u': int(data['u'])}).first()
        if row:
            stats = {'answered': int(row[0] or 0), 'correct': int(row[1] or 0)}
        srow = db.session.execute(_t('SELECT current_streak, max_streak FROM streak_records WHERE user_id=:u'),
                                  {'u': int(data['u'])}).first()
        if srow:
            stats.update({'streak': int(srow[0] or 0), 'max_streak': int(srow[1] or 0)})
    except Exception:
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
    _track('parent_offer_view', {'child_user_id': data['u']})
    from services.billing_plans import PLANS
    return render_template('parent/offer.html', child=child, stats=stats, child_id=data['u'],
                           plans=[PLANS['student_month'], PLANS['student_year'], PLANS['family_month']])


def install(app) -> None:
    if not ENABLED or app.extensions.get('parent_offer_installed'):
        return
    app.extensions['parent_offer_installed'] = True
    if 'parent_offer' not in app.blueprints:
        app.register_blueprint(parent_offer_bp)
    logger.info('PARENT_OFFER_V1 registered (/parent/offer-link, /parent/offer/<token>)')
