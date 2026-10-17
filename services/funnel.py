# -*- coding: utf-8 -*-
"""FUNNEL_V1 (18.10.2026) — своя воронка вместо Яндекс Метрики/Директа.

Что делает:
  * таблица funnel_events — события воронки и монетизации;
  * before_request: anon_id в session, первый визит в сессии → событие `visit`
    с referrer и ?ref=/utm_* и классификацией источника;
  * сигнал flask_login.user_logged_in → `signup`, если users.created_at моложе
    2 минут; источник первого визита копируется в users.acq_source/acq_ref;
  * серверные обёртки существующих view-функций (без правки шаблонов):
      intake.answer_intake / intake.submit_intake_anchor → `intake_done`,
      /daily_tasks/<id>/submit и /submit_ai → `first_task_solved`;
  * POST /api/ev — клиентские события из белого списка;
  * window.track(name, props) — вставляется в HTML after_request'ом (как
    трекер в services/site_stats.py), base.html не правим;
  * payment_success(...) — для вызова из webhook ЮKassa (задача 19.10).

Откат: FUNNEL_ENABLED=0 — ни таблиц, ни хуков, ни маршрутов.
Любая ошибка БД — fail-open (сайт не падает, событие теряется).
Не трогает серии, XP, лидерборд, друзей, чат.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request, session
from flask_login import current_user, user_logged_in
from sqlalchemy import text

logger = logging.getLogger(__name__)

bp = Blueprint('funnel', __name__)

ENABLED = os.environ.get('FUNNEL_ENABLED', '1') != '0'
SIGNUP_WINDOW = timedelta(minutes=2)

UTM_KEYS = ('utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'yclid')
# события, которые считаются «первыми» и дедуплицируются по (user_id, event)
ONCE_EVENTS = ('signup', 'intake_done', 'first_task_solved')
# события, которые можно присылать с клиента через /api/ev
CLIENT_EVENTS = ('intake_done', 'first_task_solved', 'limit_hit', 'paywall_view',
                 'subscribe_view', 'founder_offer_click', 'mock_start', 'mock_complete',
                 'daily_tasks_start_yes', 'daily_tasks_start_later')
SOURCES = ('tg', 'teacher', 'parent', 'referral', 'organic', 'social', 'direct_visit', 'internal')

_SEARCH_HOSTS = ('yandex.', 'ya.ru', 'google.', 'bing.com', 'duckduckgo.', 'mail.ru/search', 'go.mail.ru')
_SOCIAL_HOSTS = ('vk.com', 'vk.ru', 't.me', 'telegram.', 'ok.ru', 'dzen.ru', 'youtube.', 'youtu.be', 'rutube.')

INJECT_TAG = ('<script>window.track=function(n,p){try{fetch("/api/ev",{method:"POST",'
              'credentials:"same-origin",headers:{"Content-Type":"application/json"},'
              'body:JSON.stringify({event:n,props:p||{}}),keepalive:true});}catch(e){}};</script>')


# ──────────────────────────── helpers ────────────────────────────
def _db():
    from models import db
    return db


def _is_pg() -> bool:
    try:
        return _db().engine.dialect.name == 'postgresql'
    except Exception:
        return False


def msk_now() -> datetime:
    return datetime.utcnow() + timedelta(hours=3)


_tables_ready = False


def ensure_tables() -> None:
    """Создаёт таблицу/индексы и поля users (идемпотентно, PG и SQLite)."""
    global _tables_ready
    if _tables_ready or not ENABLED:
        return
    db = _db()
    pg = _is_pg()
    serial = 'SERIAL PRIMARY KEY' if pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    ts_default = 'TIMESTAMP NOT NULL DEFAULT NOW()' if pg else 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP'
    props_type = 'JSONB' if pg else 'TEXT'
    stmts = [
        f"""CREATE TABLE IF NOT EXISTS funnel_events (
                id {serial},
                user_id INTEGER,
                anon_id VARCHAR(36),
                event VARCHAR(40) NOT NULL,
                props {props_type},
                source VARCHAR(40),
                ref VARCHAR(80),
                path VARCHAR(200),
                referrer VARCHAR(300),
                created_at {ts_default}
            )""",
        "CREATE INDEX IF NOT EXISTS ix_fe_event_created ON funnel_events (event, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_fe_user ON funnel_events (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_fe_anon ON funnel_events (anon_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_fe_user_once ON funnel_events (user_id, event) "
        "WHERE event IN ('signup','intake_done','first_task_solved') AND user_id IS NOT NULL",
    ]
    user_cols = [
        ('acq_source', 'VARCHAR(40)'),
        ('acq_ref', 'VARCHAR(80)'),
        ('invited_by', 'INTEGER'),
    ]
    try:
        for s in stmts:
            db.session.execute(text(s))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning('funnel.ensure_tables: %r', e)
        return
    for col, typ in user_cols:
        try:
            if pg:
                db.session.execute(text(f'ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {typ}'))
            else:
                cols = [r[1] for r in db.session.execute(text('PRAGMA table_info(users)')).fetchall()]
                if col not in cols:
                    db.session.execute(text(f'ALTER TABLE users ADD COLUMN {col} {typ}'))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.warning('funnel.ensure_tables users.%s: %r', col, e)
    _tables_ready = True


def classify_source(ref: str | None, utm: dict | None, referrer: str | None) -> str:
    """tg / teacher / parent / referral / organic / social / direct_visit / internal."""
    ref = (ref or '').strip().lower()
    utm = utm or {}
    if ref:
        if ref.startswith(('tg', 'telegram')):
            return 'tg'
        if ref.startswith('teacher'):
            return 'teacher'
        if ref.startswith('parent'):
            return 'parent'
        if ref.startswith(('u_', 'ref_', 'friend')):
            return 'referral'
    src = (utm.get('utm_source') or '').lower()
    if src:
        if 'telegram' in src or src in ('tg', 't.me'):
            return 'tg'
        if 'vk' in src or 'ok.ru' in src or 'youtube' in src or 'dzen' in src:
            return 'social'
        return 'referral' if 'ref' in src else 'social'
    host = ''
    try:
        host = (urlparse(referrer or '').netloc or '').lower()
    except Exception:
        host = ''
    if not host:
        return 'direct_visit'
    own = (request.host or '').lower() if request else ''
    if own and (host == own or host.endswith('formyla.net') or host.endswith('onrender.com')):
        return 'internal'
    if any(h in host for h in _SEARCH_HOSTS):
        return 'organic'
    if any(h in host for h in _SOCIAL_HOSTS):
        return 'tg' if ('t.me' in host or 'telegram' in host) else 'social'
    return 'referral'


def _user_id_or_none():
    try:
        if current_user.is_authenticated and not getattr(current_user, 'is_guest', False):
            return int(current_user.id)
    except Exception:
        pass
    return None


def track(event: str, props: dict | None = None, user_id: int | None = None,
          source: str | None = None, ref: str | None = None) -> bool:
    """Записать событие. Возвращает True, если строка вставлена. Fail-open."""
    if not ENABLED or not event:
        return False
    db = _db()
    try:
        ensure_tables()
        uid = user_id if user_id is not None else _user_id_or_none()
        acq = session.get('acq') or {} if session else {}
        src = source or acq.get('source')
        rf = ref or acq.get('ref')
        path = (request.path if request else '')[:200]
        referrer = ((request.referrer if request else '') or '')[:300]
        payload = json.dumps(props or {}, ensure_ascii=False)
        if _is_pg():
            sql = ('INSERT INTO funnel_events (user_id, anon_id, event, props, source, ref, path, referrer) '
                   'VALUES (:u, :a, :e, CAST(:p AS JSONB), :s, :r, :path, :rr) ON CONFLICT DO NOTHING')
        else:
            sql = ('INSERT OR IGNORE INTO funnel_events (user_id, anon_id, event, props, source, ref, path, referrer) '
                   'VALUES (:u, :a, :e, :p, :s, :r, :path, :rr)')
        res = db.session.execute(text(sql), {
            'u': uid, 'a': (session.get('anon_id') if session else None),
            'e': str(event)[:40], 'p': payload, 's': (src or None),
            'r': (rf or None), 'path': path, 'rr': referrer or None,
        })
        db.session.commit()
        return bool(getattr(res, 'rowcount', 0))
    except Exception as e:
        db.session.rollback()
        logger.warning('funnel.track(%s): %r', event, e)
        return False


def payment_success(user_id: int, plan_code: str, amount, payment_id: str | None = None,
                    props: dict | None = None) -> bool:
    """Вызывать из webhook ЮKassa после подтверждения платежа (идемпотентно по payment_id)."""
    p = dict(props or {})
    p.update({'plan': plan_code, 'amount': float(amount or 0), 'payment_id': payment_id})
    if payment_id:
        try:
            ensure_tables()
            like = f'%"payment_id": "{payment_id}"%'
            r = _db().session.execute(text(
                "SELECT 1 FROM funnel_events WHERE event = 'payment_success' AND CAST(props AS TEXT) LIKE :l LIMIT 1"
            ), {'l': like}).first()
            if r:
                return False
        except Exception:
            _db().session.rollback()
    return track('payment_success', p, user_id=user_id)


# ──────────────────────────── hooks ────────────────────────────
def _capture_visit():
    """Первый запрос в сессии: anon_id, источник, событие visit."""
    try:
        if request.method != 'GET':
            return
        p = request.path or ''
        if p.startswith(('/static/', '/api/', '/sw.js', '/site.webmanifest', '/favicon', '/admin/')):
            return
        if 'anon_id' not in session:
            session['anon_id'] = str(uuid.uuid4())
            session.permanent = True
        ref = (request.args.get('ref') or '')[:80] or None
        utm = {k: request.args.get(k)[:120] for k in UTM_KEYS if request.args.get(k)}
        if ref or utm:
            if 'acq' not in session:
                session['acq'] = {'source': classify_source(ref, utm, request.referrer),
                                  'ref': ref or utm.get('utm_campaign') or utm.get('utm_source')}
        if session.get('visit_logged'):
            return
        session['visit_logged'] = True
        acq = session.get('acq') or {}
        src = acq.get('source') or classify_source(None, None, request.referrer)
        if 'acq' not in session:
            session['acq'] = {'source': src, 'ref': None}
        track('visit', {'utm': utm} if utm else None, source=src, ref=acq.get('ref'))
    except Exception as e:
        logger.debug('funnel._capture_visit skipped: %r', e)


def _on_login(sender, user, **extra):
    """signup — вход в течение 2 минут после создания пользователя."""
    try:
        created = getattr(user, 'created_at', None)
        if not created or datetime.utcnow() - created > SIGNUP_WINDOW:
            return
        via = 'telegram' if getattr(user, 'telegram_id', None) else 'email'
        inserted = track('signup', {'via': via, 'role': getattr(user, 'role', None)}, user_id=user.id)
        if inserted:
            acq = session.get('acq') or {}
            _db().session.execute(text(
                'UPDATE users SET acq_source = :s, acq_ref = :r WHERE id = :u AND acq_source IS NULL'
            ), {'s': acq.get('source') or 'direct_visit', 'r': acq.get('ref'), 'u': user.id})
            _db().session.commit()
    except Exception as e:
        _db().session.rollback()
        logger.warning('funnel._on_login: %r', e)


def _json_of(resp):
    try:
        r = resp[0] if isinstance(resp, tuple) else resp
        return r.get_json(silent=True) if hasattr(r, 'get_json') else None
    except Exception:
        return None


def _wrap_intake(app):
    for ep in ('intake.answer_intake', 'intake.submit_intake_anchor'):
        orig = app.view_functions.get(ep)
        if orig is None or getattr(orig, '_funnel_wrapped', False):
            continue

        def make(o):
            def wrapper(*a, **kw):
                resp = o(*a, **kw)
                try:
                    data = _json_of(resp)
                    if data and data.get('done') and data.get('result'):
                        res = data.get('result') or {}
                        track('intake_done', {'anchors_correct': res.get('anchors_correct'),
                                              'daily_tasks': res.get('daily_tasks')})
                except Exception as e:
                    logger.debug('funnel intake wrapper: %r', e)
                return resp
            wrapper.__name__ = getattr(o, '__name__', 'view')
            wrapper._funnel_wrapped = True
            return wrapper
        app.view_functions[ep] = make(orig)


def _wrap_daily_submit(app):
    """Оборачиваем /daily_tasks/<id>/submit и /submit_ai по правилам url_map."""
    targets = []
    for rule in app.url_map.iter_rules():
        r = str(rule.rule)
        if r.startswith('/daily_tasks/') and (r.endswith('/submit') or r.endswith('/submit_ai')):
            targets.append(rule.endpoint)
    for ep in set(targets):
        orig = app.view_functions.get(ep)
        if orig is None or getattr(orig, '_funnel_wrapped', False):
            continue

        def make(o):
            def wrapper(*a, **kw):
                resp = o(*a, **kw)
                try:
                    data = _json_of(resp)
                    if data and data.get('is_correct') is True:
                        track('first_task_solved', {'ai': 'submit_ai' in (request.path or '')})
                except Exception as e:
                    logger.debug('funnel daily wrapper: %r', e)
                return resp
            wrapper.__name__ = getattr(o, '__name__', 'view')
            wrapper._funnel_wrapped = True
            return wrapper
        app.view_functions[ep] = make(orig)


# ──────────────────────────── API ────────────────────────────
@bp.route('/api/ev', methods=['POST'])
def api_event():
    if _user_id_or_none() is None:
        return jsonify(ok=False), 401
    data = request.get_json(silent=True) or {}
    ev = str(data.get('event') or '')[:40]
    if ev not in CLIENT_EVENTS:
        return jsonify(ok=False, error='event_not_allowed'), 400
    props = data.get('props') if isinstance(data.get('props'), dict) else {}
    return jsonify(ok=track(ev, props))


# ──────────────────────────── install ────────────────────────────
def install(app) -> None:
    if not ENABLED or app.extensions.get('funnel_installed'):
        return
    app.extensions['funnel_installed'] = True
    if 'funnel' not in app.blueprints:
        app.register_blueprint(bp)
    try:
        with app.app_context():
            ensure_tables()
    except Exception as e:
        logger.warning('funnel: ensure_tables at startup failed: %r', e)

    app.before_request(_capture_visit)
    user_logged_in.connect(_on_login, app)

    # обёртки view-функций — после того, как все blueprint'ы зарегистрированы
    def _late_wrap():
        try:
            _wrap_intake(app)
            _wrap_daily_submit(app)
        except Exception as e:
            logger.warning('funnel: wrapping views failed: %r', e)
    app.before_request(_once(_late_wrap))

    @app.after_request
    def _inject_track(resp):
        try:
            if (resp.status_code == 200 and resp.mimetype == 'text/html'
                    and not resp.direct_passthrough and not request.path.startswith('/static/')):
                html = resp.get_data(as_text=True)
                if 'window.track=' not in html:
                    idx = html.rfind('</body>')
                    if idx != -1:
                        resp.set_data(html[:idx] + INJECT_TAG + html[idx:])
        except Exception as e:
            logger.debug('funnel inject skipped: %r', e)
        return resp

    logger.info('FUNNEL_V1 registered (/api/ev, funnel_events)')


def _once(fn):
    state = {'done': False}

    def runner():
        if not state['done']:
            state['done'] = True
            fn()
    runner.__name__ = 'funnel_late_wrap'
    return runner
