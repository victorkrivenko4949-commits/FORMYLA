# -*- coding: utf-8 -*-
"""Readiness survey after intake and the admin Surveys section."""
import hashlib
import hmac
import json
import secrets
from flask import Blueprint, abort, current_app, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import inspect, text
from models import db

surveys_bp = Blueprint('surveys', __name__)
OPTIONS = {
    'yes': 'Да, готов!',
    'try': 'Постараюсь, но не обещаю каждый день.',
    'not_yet': 'Пока не готов.',
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS readiness_survey_answers (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    answer VARCHAR(16) NOT NULL CHECK (answer IN ('yes', 'try', 'not_yet')),
    answered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def ensure_table():
    engine = db.engine
    if current_app.extensions.get('readiness_schema_engine') is engine:
        return
    with engine.begin() as conn:
        conn.execute(text(SCHEMA))
    current_app.extensions['readiness_schema_engine'] = engine


def completed_intake(prep_state):
    if isinstance(prep_state, str):
        try:
            prep_state = json.loads(prep_state)
        except (ValueError, TypeError):
            return False
    if not isinstance(prep_state, dict):
        return False
    intake = prep_state.get('intake')
    return (isinstance(intake, dict) and bool(intake.get('completed'))
            and not bool(intake.get('skipped')))


def _intake_completed(user_id):
    from models_curator import CuratorState
    state = CuratorState.query.filter_by(user_id=user_id).first()
    return completed_intake(getattr(state, 'prep_state', None))


def _readiness_csrf_token(user_id):
    """Stateless CSRF-токен опроса готовности: HMAC(SECRET_KEY, user_id).

    Токен намеренно НЕ хранится во Flask-сессии. Раньше /pending делал
    session.setdefault(...), но на загрузке страницы /pending гонится с
    параллельными API-поллингами (insights, site-notice, wb_call и др.),
    а при постоянной сессии (SESSION_REFRESH_EACH_REQUEST) КАЖДЫЙ ответ
    перезаписывает куку сессии своим снапшотом. Если ответ поллинга
    приходил после ответа /pending — токен стирался из куки, и «Отправить»
    падал с 403 «Обнови страницу и попробуй ещё раз» (гонка воспроизводилась
    и на десктопе, и на телефоне; см. логи Render 22-23.10.2026).

    HMAC от серверного SECRET_KEY даёт тот же уровень защиты от CSRF:
    атакующий со стороннего сайта не может ни прочитать токен (GET /pending
    под логином, same-origin), ни вычислить его без SECRET_KEY.
    """
    secret = current_app.config.get('SECRET_KEY') or ''
    if isinstance(secret, str):
        secret = secret.encode('utf-8')
    msg = 'readiness_survey_csrf:{}'.format(user_id).encode('utf-8')
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


@surveys_bp.get('/api/readiness-survey/pending')
@login_required
def pending():
    if getattr(current_user, 'is_guest', False) or not _intake_completed(current_user.id):
        response = jsonify(pending=False)
    else:
        ensure_table()
        answered = db.session.execute(text(
            'SELECT answer FROM readiness_survey_answers WHERE user_id = :uid'
        ), {'uid': current_user.id}).first()
        token = _readiness_csrf_token(current_user.id)
        response = jsonify(pending=answered is None, csrf=token)
    response.headers['Cache-Control'] = 'no-store'
    return response


@surveys_bp.post('/api/readiness-survey')
@login_required
def answer():
    if getattr(current_user, 'is_guest', False):
        abort(403)
    expected = _readiness_csrf_token(current_user.id)
    supplied = request.headers.get('X-Readiness-CSRF', '')
    if not supplied or not secrets.compare_digest(expected, supplied):
        return jsonify(ok=False, error='Обнови страницу и попробуй ещё раз.'), 403
    data = request.get_json(silent=True)
    choice = data.get('answer') if isinstance(data, dict) else None
    if not isinstance(choice, str) or choice not in OPTIONS:
        return jsonify(ok=False, error='Выбери один из вариантов ответа.'), 400
    if not _intake_completed(current_user.id):
        return jsonify(ok=False, error='Сначала пройди анкету.'), 409
    ensure_table()
    try:
        db.session.execute(text(
            'INSERT INTO readiness_survey_answers (user_id, answer) VALUES (:uid, :answer) '
            'ON CONFLICT (user_id) DO NOTHING'
        ), {'uid': current_user.id, 'answer': choice})
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Readiness survey answer failed')
        return jsonify(ok=False, error='Не удалось сохранить ответ. Попробуй ещё раз.'), 503
    return jsonify(ok=True)


def distribution(options, counts):
    total = sum(int(counts.get(key, 0)) for key in options)
    return {'total': total, 'options': [
        {'label': label, 'count': int(counts.get(key, 0)),
         'percent': round(100 * int(counts.get(key, 0)) / total, 1) if total else 0}
        for key, label in options.items()
    ]}


def load_stats():
    ensure_table()
    counts = dict(db.session.execute(text(
        'SELECT answer, COUNT(*) FROM readiness_survey_answers GROUP BY answer'
    )).all())
    readiness = distribution(OPTIONS, counts)
    readiness['rows'] = db.session.execute(text(
        'SELECT a.user_id, u.nickname, a.answer, a.answered_at '
        'FROM readiness_survey_answers a JOIN users u ON u.id = a.user_id '
        'ORDER BY a.answered_at DESC, a.user_id DESC LIMIT 200'
    )).mappings().all()
    ratings = {n: str(n) + ' / 5' for n in range(1, 6)}
    site = distribution(ratings, {})
    site.update(avg=0, rows=[], pending=0)
    if inspect(db.engine).has_table('site_feedback'):
        counts = dict(db.session.execute(text(
            'SELECT rating, COUNT(*) FROM site_feedback '
            'WHERE answered_at IS NOT NULL AND rating BETWEEN 1 AND 5 GROUP BY rating'
        )).all())
        site.update(distribution(ratings, counts))
        site['avg'] = round(sum(n * counts.get(n, 0) for n in ratings) / site['total'], 2) if site['total'] else 0
        site['pending'] = db.session.execute(text(
            'SELECT COUNT(*) FROM site_feedback WHERE answered_at IS NULL'
        )).scalar()
        site['rows'] = db.session.execute(text(
            'SELECT f.user_id, u.nickname, f.rating, f.feedback_text, f.answered_at '
            'FROM site_feedback f JOIN users u ON u.id = f.user_id '
            'WHERE f.answered_at IS NOT NULL '
            'ORDER BY f.answered_at DESC, f.user_id DESC LIMIT 200'
        )).mappings().all()
    return site, readiness


@surveys_bp.get('/admin/users/surveys')
@login_required
def admin_surveys():
    if getattr(current_user, 'is_admin', False) is not True:
        abort(403)
    site, readiness = load_stats()
    response = current_app.make_response(render_template(
        'admin/surveys.html', site=site, readiness=readiness, options=OPTIONS))
    response.headers['Cache-Control'] = 'no-store'
    return response


def install_surveys(app, register=None):
    if app.extensions.get('surveys_installed'):
        return
    app.extensions['surveys_installed'] = True
    if 'surveys' not in app.blueprints:
        if register is None:
            app.register_blueprint(surveys_bp)
        else:
            register(app, surveys_bp)

    @app.after_request
    def surveys_ui(response):
        if (response.status_code != 200 or response.direct_passthrough
                or response.mimetype != 'text/html' or not current_user.is_authenticated):
            return response
        body = response.get_data(as_text=True)
        if '</body>' not in body:
            return response
        extra = ''
        if getattr(current_user, 'is_admin', False) and request.path.startswith('/admin/'):
            if 'id="ft-surveys-nav"' not in body:
                extra += ('<a id="ft-surveys-nav" href="/admin/users/surveys" '
                          'style="position:fixed;right:18px;bottom:74px;z-index:30000;'
                          'padding:10px 16px;border-radius:12px;background:#f4b942;'
                          'color:#0b1020;font-weight:800;text-decoration:none;">Опросы</a>')
        elif not getattr(current_user, 'is_guest', False) and 'id="ft-feedback-overlay"' in body:
            if 'id="ft-readiness-script"' not in body:
                extra += ('<script id="ft-readiness-script" '
                          'src="/static/js/readiness_survey.js?v=1" defer></script>')
        if extra:
            response.set_data(body.replace('</body>', extra + '</body>', 1))
            response.headers['Cache-Control'] = 'private, no-store'
        return response
