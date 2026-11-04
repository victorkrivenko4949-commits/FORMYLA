# -*- coding: utf-8 -*-
"""EXIT_QUESTION_V1 (2026-11-05) — короткий вопрос «что остановило?» прямо на сайте.

Когда спрашиваем (не чаще раза в 3 дня, каждый случай — один раз):
  * checkout — человек создал платёж ЮKassa (yookassa_payments), он не прошёл
    за 20 минут, и после него успешной оплаты нет: «Что остановило?»;
  * comeback — человек вернулся после перерыва от 7 дней (по трекеру времени
    site_time_sections): «Тебя не было N дней. Что помешало заходить?».

Вопрос — карточка внизу экрана, не блокирует сайт, её можно пропустить
(пропуск тоже записываем, чтобы не спрашивать снова). Не показываем админам,
гостям, на /admin, /intake, /payments, /schedule.

Ответы — таблица exit_answers; их читает статистика («Путь человека»,
«Ушли и не вернулись», «Опросы и оценки»): там это главная причина ухода,
потому что её назвал сам человек.

Откат: EXIT_QUESTION_ENABLED=0 — ни скрипта, ни маршрутов.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, current_app, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

ENABLED = os.environ.get('EXIT_QUESTION_ENABLED', '1') != '0'
bp = Blueprint('exit_question', __name__)

COOLDOWN_DAYS = 3
CHECKOUT_WAIT_MIN = 20
COMEBACK_GAP_DAYS = 7
SKIP_PREFIXES = ('/admin', '/intake', '/payments', '/schedule', '/static', '/api', '/login', '/logout')

OPTIONS = {
    'checkout': {
        'expensive': 'Дорого',
        'try_free': 'Хочу сначала попробовать бесплатно',
        'parents': 'Нужно спросить родителей',
        'payment_error': 'Не получилось оплатить (ошибка)',
        'changed_mind': 'Передумал',
        'other': 'Другое',
    },
    'comeback': {
        'no_time': 'Не было времени',
        'boring': 'Стало скучно',
        'too_hard': 'Слишком сложно',
        'too_easy': 'Слишком легко',
        'forgot': 'Забыл про сайт',
        'unclear': 'Не понял, что делать дальше',
        'other': 'Другое',
    },
}
TRIGGER_TITLES = {'checkout': 'После брошенной оплаты', 'comeback': 'После перерыва 7+ дней'}

_ready_engine = None


def _db():
    from models import db
    return db


def _has_table(name: str) -> bool:
    try:
        return inspect(_db().engine).has_table(name)
    except Exception:
        return False


def ensure_table() -> None:
    global _ready_engine
    db = _db()
    if _ready_engine is db.engine:
        return
    pg = db.engine.dialect.name == 'postgresql'
    serial = 'SERIAL PRIMARY KEY' if pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    with db.engine.begin() as conn:
        conn.execute(text(f"""CREATE TABLE IF NOT EXISTS exit_answers (
            id {serial},
            user_id INTEGER NOT NULL,
            kind VARCHAR(16) NOT NULL,
            trigger_key VARCHAR(64) NOT NULL,
            answer VARCHAR(24),
            answer_text VARCHAR(500),
            status VARCHAR(12) NOT NULL,
            gap_days INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, kind, trigger_key)
        )"""))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_exit_answers_user ON exit_answers (user_id)'))
    _ready_engine = db.engine


def _dt(v):
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace('T', ' ')[:26]) if v else None
    except Exception:
        return None


def _d(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def pending_for(user_id: int, now: datetime | None = None):
    """Какой вопрос сейчас задать: {'trigger', 'key', 'gap'} или None."""
    now = now or datetime.utcnow()
    ensure_table()
    s = _db().session
    rows = s.execute(text('SELECT kind, trigger_key, created_at FROM exit_answers WHERE user_id = :u'),
                     {'u': user_id}).fetchall()
    done = {(r[0], r[1]) for r in rows}
    last_asked = max((_dt(r[2]) for r in rows if _dt(r[2])), default=None)
    if last_asked and now - last_asked < timedelta(days=COOLDOWN_DAYS):
        return None

    if _has_table('yookassa_payments'):
        pays = s.execute(text('SELECT order_id, status, created_at FROM yookassa_payments WHERE user_id = :u '
                              'ORDER BY created_at'), {'u': user_id}).fetchall()
        last_fail = None
        for oid, st, t in pays:
            t = _dt(t)
            if st == 'succeeded':
                last_fail = None          # после неудачи всё-таки оплатил — не спрашиваем
            elif t and now - t >= timedelta(minutes=CHECKOUT_WAIT_MIN):
                last_fail = str(oid)
        if last_fail and ('checkout', last_fail) not in done:
            return {'trigger': 'checkout', 'key': last_fail, 'gap': None}

    if _has_table('site_time_sections'):
        today = (now + timedelta(hours=3)).date()
        prev = s.execute(text("SELECT MAX(day) FROM site_time_sections WHERE user_id = :u AND section = 'general' "
                              "AND seconds > 0 AND day < :d"), {'u': user_id, 'd': today}).scalar()
        prev = _d(prev)
        if prev:
            gap = (today - prev).days
            if gap >= COMEBACK_GAP_DAYS and ('comeback', prev.isoformat()) not in done:
                return {'trigger': 'comeback', 'key': prev.isoformat(), 'gap': gap}
    return None


def question_text(p: dict) -> str:
    if p['trigger'] == 'checkout':
        return 'Ты начал оформлять Premium, но оплата не прошла. Что остановило?'
    return f"Тебя не было {p['gap']} дн. Что помешало заходить?"


def _csrf(user_id: int) -> str:
    secret = current_app.config.get('SECRET_KEY') or ''
    if not secret:
        abort(500)
    if isinstance(secret, str):
        secret = secret.encode('utf-8')
    return hmac.new(secret, f'exit_question_csrf:{user_id}'.encode(), hashlib.sha256).hexdigest()


def _eligible() -> bool:
    return bool(current_user.is_authenticated and not getattr(current_user, 'is_guest', False)
                and getattr(current_user, 'is_admin', False) is not True)


@bp.get('/api/exit-question/pending')
@login_required
def api_pending():
    data = {'pending': False}
    if _eligible():
        try:
            p = pending_for(current_user.id)
        except Exception as e:  # noqa: BLE001 — вопрос не должен ломать сайт
            _db().session.rollback()
            logger.warning('exit_question.pending: %r', e)
            p = None
        if p:
            data = {'pending': True, 'trigger': p['trigger'], 'key': p['key'], 'question': question_text(p),
                    'options': [{'value': k, 'label': v} for k, v in OPTIONS[p['trigger']].items()],
                    'csrf': _csrf(current_user.id)}
    resp = jsonify(data)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@bp.post('/api/exit-question')
@login_required
def api_answer():
    if not _eligible():
        abort(403)
    if not secrets.compare_digest(_csrf(current_user.id), request.headers.get('X-Exit-CSRF', '')):
        return jsonify(ok=False, error='Обнови страницу и попробуй ещё раз.'), 403
    data = request.get_json(silent=True) or {}
    p = pending_for(current_user.id)
    # отвечать можно только на тот вопрос, который сервер сейчас задаёт
    if not p or data.get('trigger') != p['trigger'] or str(data.get('key')) != p['key']:
        return jsonify(ok=True, stale=True)
    dismiss = bool(data.get('dismiss'))
    answer = None if dismiss else data.get('answer')
    if not dismiss and answer not in OPTIONS[p['trigger']]:
        return jsonify(ok=False, error='Выбери вариант или нажми «Пропустить».'), 400
    note = None if dismiss else (str(data.get('text') or '').strip()[:500] or None)
    try:
        _db().session.execute(text(
            'INSERT INTO exit_answers (user_id, kind, trigger_key, answer, answer_text, status, gap_days, created_at) '
            'VALUES (:u, :t, :k, :a, :x, :s, :g, :c)'),
            {'u': current_user.id, 't': p['trigger'], 'k': p['key'], 'a': answer, 'x': note,
             's': 'dismissed' if dismiss else 'answered', 'g': p['gap'], 'c': datetime.utcnow()})
        _db().session.commit()
    except Exception as e:  # noqa: BLE001 — например, двойное нажатие
        _db().session.rollback()
        logger.info('exit_question.answer: %r', e)
    return jsonify(ok=True)


def _inject(resp):
    try:
        if (resp.status_code != 200 or resp.direct_passthrough or resp.mimetype != 'text/html'
                or request.method != 'GET' or (request.path or '').startswith(SKIP_PREFIXES) or not _eligible()):
            return resp
        body = resp.get_data(as_text=True)
        if '</body>' not in body or 'id="ft-exit-q-script"' in body:
            return resp
        tag = '<script id="ft-exit-q-script" src="/static/js/exit_question.js?v=1" defer></script>'
        resp.set_data(body.replace('</body>', tag + '</body>', 1))
    except Exception as e:  # noqa: BLE001
        logger.debug('exit_question inject skipped: %r', e)
    return resp


def install(app) -> None:
    if not ENABLED or app.extensions.get('exit_question_installed'):
        return
    app.extensions['exit_question_installed'] = True
    if 'exit_question' not in app.blueprints:
        app.register_blueprint(bp)
    try:
        with app.app_context():
            ensure_table()
    except Exception as e:  # noqa: BLE001
        logger.warning('exit_question: ensure_table at startup failed: %r', e)
    app.after_request(_inject)
    logger.info('EXIT_QUESTION_V1 registered (/api/exit-question)')
