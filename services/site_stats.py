# -*- coding: utf-8 -*-
"""SECTION_STATS_V1 — учёт времени по разделам сайта, опрос «102 метода»,
история чертежей GeoExact и админ-таблица по разделам.

Подключение (ОДНА строка в самом конце app.py, после регистрации всех blueprint'ов):

    from services.site_stats import register as _register_site_stats; _register_site_stats(app)

Модуль ничего не требует менять в base.html / geoexact: скрипт трекера
подставляется в HTML-ответы автоматически (after_request), старый heartbeat
/api/track/site-time переопределяется (чтобы не было двойного счёта), а
готовые чертежи GeoExact перехватываются на /geometry/draw/status/<id>.

Разделы:
    general    — весь сайт (сумма всех секунд; пишется в users.site_seconds_total)
    daily      — /daily_tasks*
    methods    — /olympiads/methods*  (102 метода, включая iframe-атлас)
    generators — /geometry/draw*      (генерация чертежей)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, date, timedelta

from flask import Blueprint, jsonify, request, render_template, abort
from flask_login import current_user, login_required
from sqlalchemy import text

logger = logging.getLogger(__name__)

SECTIONS = ('daily', 'methods', 'generators', 'other')
SECTION_TITLES = {
    'general': 'Общая статистика',
    'daily': 'Задачи дня',
    'methods': '102 метода',
    'generators': 'Генераторы чертежей',
    'other': 'Остальные страницы',
}
SECTION_PREFIXES = (
    ('/daily_tasks', 'daily'),
    ('/olympiads/methods', 'methods'),
    ('/geometry/draw', 'generators'),
    ('/geometry/drawings', 'generators'),
)

MAX_BEAT_SEC = 120                   # один удар не может принести больше 2 минут
METHODS_FEEDBACK_MIN_SEC = 15 * 60   # вопрос про 102 метода после 15 минут внутри методов

METHODS_FEEDBACK_QUESTION = 'Насколько понятно объяснены методы?'
METHODS_FEEDBACK_SUBTITLE = ('Ты провёл в разделе «102 метода» уже больше 15 минут. '
                             'Оцени, насколько понятным языком написаны разборы: '
                             '1 — слишком сложно, ничего не понял; 5 — всё ясно с первого раза. '
                             'Если где-то было тяжело — напиши, в каком методе.')

bp = Blueprint('site_stats', __name__)


# ──────────────────────────── helpers ────────────────────────────
def _db():
    from models import db
    return db


def _is_pg() -> bool:
    try:
        return _db().engine.dialect.name == 'postgresql'
    except Exception:
        return False


def _is_admin() -> bool:
    try:
        from routes.admin_support import _is_admin as _adm
        return bool(_adm())
    except Exception:
        pass
    nick = (getattr(current_user, 'nickname', '') or '').lower()
    return bool(getattr(current_user, 'is_admin', False)) or nick in (
        'pavelznaka', 'victorkrivenko', 'victor', 'nikolaev', 'lavrik')


def _real_user() -> bool:
    try:
        return bool(current_user.is_authenticated and not getattr(current_user, 'is_guest', False))
    except Exception:
        return False


def section_for_path(path: str) -> str:
    p = (path or '').split('?')[0]
    for prefix, sec in SECTION_PREFIXES:
        if p == prefix or p.startswith(prefix):
            return sec
    return 'other'


_tables_ready = False


def ensure_tables():
    """Создаёт таблицы модуля (идемпотентно, и на Postgres, и на SQLite)."""
    global _tables_ready
    if _tables_ready:
        return
    db = _db()
    pg = _is_pg()
    serial = 'SERIAL PRIMARY KEY' if pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    ts_default = 'TIMESTAMP NOT NULL DEFAULT NOW()' if pg else 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP'
    ts_null = 'TIMESTAMP' if pg else 'DATETIME'
    stmts = [
        """CREATE TABLE IF NOT EXISTS site_time_sections (
                user_id INTEGER NOT NULL,
                section VARCHAR(24) NOT NULL,
                day DATE NOT NULL,
                seconds INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, section, day)
            )""",
        """CREATE TABLE IF NOT EXISTS site_time_beat (
                user_id INTEGER PRIMARY KEY,
                last_beat REAL NOT NULL DEFAULT 0,
                last_section VARCHAR(24),
                last_page VARCHAR(160)
            )""",
        f"""CREATE TABLE IF NOT EXISTS section_feedback (
                id {serial},
                user_id INTEGER NOT NULL,
                section VARCHAR(24) NOT NULL,
                rating INTEGER,
                feedback_text TEXT,
                asked_at {ts_default},
                answered_at {ts_null},
                UNIQUE (user_id, section)
            )""",
        f"""CREATE TABLE IF NOT EXISTS geo_drawing_history (
                id {serial},
                user_id INTEGER NOT NULL,
                job_id VARCHAR(80) NOT NULL UNIQUE,
                problem_text TEXT,
                with_aux BOOLEAN NOT NULL DEFAULT FALSE,
                svg TEXT,
                svg_base TEXT,
                measured TEXT,
                created_at {ts_default}
            )""",
        "CREATE INDEX IF NOT EXISTS ix_geo_hist_user ON geo_drawing_history (user_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_sts_user ON site_time_sections (user_id)",
    ]
    try:
        for s in stmts:
            db.session.execute(text(s))
        db.session.commit()
        _tables_ready = True
    except Exception as e:
        db.session.rollback()
        logger.warning('site_stats.ensure_tables: %r', e)


def _msk_today() -> date:
    return (datetime.utcnow() + timedelta(hours=3)).date()


# ──────────────────────────── core: credit time ────────────────────────────
def credit_time(user_id: int, section: str, claimed_sec: int, page: str = '') -> dict:
    """Начисляет секунды пользователю с защитой от двойного счёта.

    Защита: по стене часов. Если две вкладки шлют удары одновременно, второй
    удар получит не больше секунд, чем реально прошло с предыдущего удара.
    Возвращает итоги: {'credited': n, 'totals': {...}}.
    """
    db = _db()
    ensure_tables()
    section = section if section in SECTIONS else 'other'
    claimed = max(0, min(int(claimed_sec or 0), MAX_BEAT_SEC))
    now = time.time()
    credited = 0
    try:
        row = db.session.execute(text(
            'SELECT last_beat FROM site_time_beat WHERE user_id = :u'), {'u': user_id}).first()
        if row is None:
            db.session.execute(text(
                'INSERT INTO site_time_beat (user_id, last_beat, last_section, last_page) '
                'VALUES (:u, :t, :s, :p)'), {'u': user_id, 't': now, 's': section, 'p': page[:160]})
            allowed = claimed
        else:
            # +3 с запас на сетевую задержку и округление клиента
            allowed = max(0.0, now - float(row[0] or 0) + 3.0)
            db.session.execute(text(
                'UPDATE site_time_beat SET last_beat = :t, last_section = :s, last_page = :p '
                'WHERE user_id = :u'), {'u': user_id, 't': now, 's': section, 'p': page[:160]})
        credited = int(min(claimed, allowed))
        if credited > 0:
            day = _msk_today()
            for sec in (section, 'general'):
                db.session.execute(text(
                    'INSERT INTO site_time_sections (user_id, section, day, seconds) '
                    'VALUES (:u, :s, :d, :n) '
                    'ON CONFLICT (user_id, section, day) DO UPDATE SET seconds = site_time_sections.seconds + :n'
                ), {'u': user_id, 's': sec, 'd': day, 'n': credited})
            # Старый суммарный счётчик users.site_seconds_total остаётся источником
            # правды для /admin/users и опроса «Как тебе сайт?» (25 мин).
            db.session.execute(text(
                'UPDATE users SET site_seconds_total = COALESCE(site_seconds_total, 0) + :n WHERE id = :u'
            ), {'u': user_id, 'n': credited})
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning('site_stats.credit_time: %r', e)
    return {'credited': credited, 'totals': user_totals(user_id)}


def user_totals(user_id: int) -> dict:
    db = _db()
    out = {k: 0 for k in ('general',) + SECTIONS}
    try:
        rows = db.session.execute(text(
            'SELECT section, SUM(seconds) FROM site_time_sections WHERE user_id = :u GROUP BY section'
        ), {'u': user_id}).fetchall()
        for sec, s in rows:
            out[str(sec)] = int(s or 0)
        r = db.session.execute(text('SELECT site_seconds_total FROM users WHERE id = :u'), {'u': user_id}).first()
        out['general'] = max(out.get('general', 0), int((r[0] if r else 0) or 0))
    except Exception as e:
        db.session.rollback()
        logger.warning('site_stats.user_totals: %r', e)
    return out


# ──────────────────────────── feedback (102 метода) ────────────────────────────
def maybe_ask_section_feedback(user_id: int, totals: dict) -> None:
    if totals.get('methods', 0) < METHODS_FEEDBACK_MIN_SEC:
        return
    db = _db()
    try:
        db.session.execute(text(
            'INSERT INTO section_feedback (user_id, section) '
            'SELECT :u, :s WHERE NOT EXISTS (SELECT 1 FROM section_feedback WHERE user_id = :u AND section = :s)'
        ), {'u': user_id, 's': 'methods'})
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning('maybe_ask_section_feedback: %r', e)


def pending_section_feedback(user_id: int):
    db = _db()
    try:
        row = db.session.execute(text(
            'SELECT section FROM section_feedback WHERE user_id = :u AND answered_at IS NULL LIMIT 1'
        ), {'u': user_id}).first()
        return str(row[0]) if row else None
    except Exception:
        db.session.rollback()
        return None


# ──────────────────────────── API ────────────────────────────
@bp.route('/api/track/beat', methods=['POST'])
def api_beat():
    """Удар трекера: {section, page, seconds}. Авторизованные (не гости)."""
    if not _real_user():
        return jsonify(ok=False), 401
    data = request.get_json(silent=True) or {}
    try:
        seconds = int(data.get('seconds', 0))
    except (TypeError, ValueError):
        seconds = 0
    if seconds <= 0:
        return jsonify(ok=False), 400
    page = str(data.get('page') or '')[:160]
    section = str(data.get('section') or '') or section_for_path(page)
    res = credit_time(current_user.id, section, seconds, page)
    totals = res['totals']
    ask = None
    fb_pending = False
    if not _is_admin():
        maybe_ask_section_feedback(current_user.id, totals)
        ask = pending_section_feedback(current_user.id)
        # старый опрос «Как тебе сайт?» (25 мин) продолжает работать
        try:
            from routes.admin_support import maybe_ask_feedback, has_pending_feedback
            maybe_ask_feedback(current_user.id, totals.get('general', 0))
            fb_pending = has_pending_feedback(current_user.id)
        except Exception:
            pass
    return jsonify(ok=True, credited=res['credited'], totals=totals,
                   ask_section_feedback=ask, feedback_pending=fb_pending)


@bp.route('/api/track/my-totals')
@login_required
def api_my_totals():
    return jsonify(ok=True, totals=user_totals(current_user.id), titles=SECTION_TITLES)


@bp.route('/api/feedback/section/pending')
@login_required
def api_section_feedback_pending():
    sec = None if _is_admin() else pending_section_feedback(current_user.id)
    return jsonify(pending=bool(sec), section=sec,
                   question=METHODS_FEEDBACK_QUESTION, subtitle=METHODS_FEEDBACK_SUBTITLE)


@bp.route('/api/feedback/section', methods=['POST'])
@login_required
def api_section_feedback_submit():
    data = request.get_json(silent=True) or {}
    try:
        rating = int(data.get('rating'))
    except (TypeError, ValueError):
        return jsonify(ok=False, error='no_rating'), 400
    if not 1 <= rating <= 5:
        return jsonify(ok=False, error='bad_rating'), 400
    section = str(data.get('section') or 'methods')[:24]
    fb_text = (data.get('text') or '')[:2000]
    db = _db()
    try:
        ensure_tables()
        r = db.session.execute(text(
            'UPDATE section_feedback SET rating = :r, feedback_text = :t, answered_at = CURRENT_TIMESTAMP '
            'WHERE user_id = :u AND section = :s AND answered_at IS NULL'
        ), {'r': rating, 't': fb_text, 'u': current_user.id, 's': section})
        db.session.commit()
        if r.rowcount == 0:
            return jsonify(ok=True, already=True)
        return jsonify(ok=True)
    except Exception as e:
        db.session.rollback()
        logger.warning('api_section_feedback_submit: %r', e)
        return jsonify(ok=False, error='db'), 500


# ──────────────────────────── история чертежей ────────────────────────────
def save_drawing(user_id: int, job_id: str, result: dict) -> None:
    if not (result and result.get('ok')):
        return
    db = _db()
    try:
        ensure_tables()
        measured = result.get('measured')
        db.session.execute(text(
            'INSERT INTO geo_drawing_history (user_id, job_id, problem_text, with_aux, svg, svg_base, measured) '
            'VALUES (:u, :j, :p, :a, :s, :sb, :m) ON CONFLICT (job_id) DO NOTHING'
        ), {'u': user_id, 'j': str(job_id)[:80],
            'p': (result.get('problem_text') or '')[:12000],
            'a': bool(result.get('with_aux')),
            's': result.get('svg') or '', 'sb': result.get('svg_base') or '',
            'm': None if measured is None else str(measured)[:200]})
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning('save_drawing: %r', e)


def drawings_count(user_id: int) -> int:
    try:
        r = _db().session.execute(text(
            'SELECT COUNT(*) FROM geo_drawing_history WHERE user_id = :u'), {'u': user_id}).first()
        return int(r[0] or 0) if r else 0
    except Exception:
        _db().session.rollback()
        return 0


@bp.route('/geometry/drawings')
@login_required
def drawings_history():
    """«Мои чертежи» — все сгенерированные пользователем чертежи."""
    ensure_tables()
    rows = _db().session.execute(text(
        'SELECT id, job_id, problem_text, with_aux, svg, svg_base, measured, created_at '
        'FROM geo_drawing_history WHERE user_id = :u ORDER BY created_at DESC LIMIT 300'
    ), {'u': current_user.id}).fetchall()
    items = []
    for r in rows:
        created = r[7]
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created)
            except Exception:
                created = None
        items.append({
            'id': r[0], 'job_id': r[1], 'problem': r[2] or '', 'with_aux': bool(r[3]),
            'svg': r[4] or r[5] or '', 'measured': r[6],
            'created': (created + timedelta(hours=3)).strftime('%d.%m.%Y %H:%M') if created else '—',
        })
    return render_template('geoexact/drawings_history.html', items=items, total=len(items))


@bp.route('/geometry/drawings/<int:item_id>/delete', methods=['POST'])
@login_required
def drawings_delete(item_id: int):
    db = _db()
    try:
        db.session.execute(text('DELETE FROM geo_drawing_history WHERE id = :i AND user_id = :u'),
                           {'i': item_id, 'u': current_user.id})
        db.session.commit()
        return jsonify(ok=True)
    except Exception:
        db.session.rollback()
        return jsonify(ok=False), 500


# ──────────────────────────── админ-статистика по разделам ────────────────────────────
@bp.route('/admin/users/sections')
@login_required
def admin_sections_stats():
    if not _is_admin():
        abort(403)
    ensure_tables()
    db = _db()
    from models import User
    users = User.query.filter(User.is_guest == False).all()  # noqa: E712
    sec_rows = db.session.execute(text(
        'SELECT user_id, section, SUM(seconds) FROM site_time_sections GROUP BY user_id, section')).fetchall()
    by_user = {}
    for uid, sec, s in sec_rows:
        by_user.setdefault(uid, {})[str(sec)] = int(s or 0)
    draw_rows = db.session.execute(text(
        'SELECT user_id, COUNT(*) FROM geo_drawing_history GROUP BY user_id')).fetchall()
    draws = {uid: int(c or 0) for uid, c in draw_rows}
    fb_rows = db.session.execute(text(
        'SELECT user_id, rating, feedback_text, answered_at FROM section_feedback WHERE section = :s'
    ), {'s': 'methods'}).fetchall()
    fb = {uid: {'rating': r, 'text': t or '', 'answered': a is not None} for uid, r, t, a in fb_rows}

    def fmt(sec):
        sec = int(sec or 0)
        h, m = divmod(sec // 60, 60)
        return f'{h} ч {m:02d} мин' if h else f'{m} мин'

    rows = []
    agg = {k: 0 for k in ('general',) + SECTIONS}
    for u in users:
        t = by_user.get(u.id, {})
        general = int(getattr(u, 'site_seconds_total', 0) or 0)
        row = {
            'id': u.id, 'nickname': u.nickname or '—',
            'general': general, 'general_f': fmt(general),
            'daily': t.get('daily', 0), 'daily_f': fmt(t.get('daily', 0)),
            'methods': t.get('methods', 0), 'methods_f': fmt(t.get('methods', 0)),
            'generators': t.get('generators', 0), 'generators_f': fmt(t.get('generators', 0)),
            'other': t.get('other', 0), 'other_f': fmt(t.get('other', 0)),
            'drawings': draws.get(u.id, 0),
            'methods_fb': fb.get(u.id),
        }
        agg['general'] += general
        for k in SECTIONS:
            agg[k] += row[k]
        rows.append(row)
    rows.sort(key=lambda r: r['general'], reverse=True)
    methods_users = sum(1 for r in rows if r['methods'] > 0)
    methods_15 = sum(1 for r in rows if r['methods'] >= METHODS_FEEDBACK_MIN_SEC)
    fb_answered = [v for v in fb.values() if v['answered'] and v['rating']]
    fb_avg = round(sum(v['rating'] for v in fb_answered) / len(fb_answered), 2) if fb_answered else 0
    totals = {k: fmt(v) for k, v in agg.items()}
    totals['drawings'] = sum(draws.values())
    totals['methods_users'] = methods_users
    totals['methods_15'] = methods_15
    totals['users'] = len(rows)
    totals['fb_answered'] = len(fb_answered)
    totals['fb_avg'] = fb_avg
    return render_template('admin/sections_stats.html', rows=rows, totals=totals,
                           titles=SECTION_TITLES, fb_question=METHODS_FEEDBACK_QUESTION)


# ──────────────────────────── register ────────────────────────────
INJECT_TAG = '<script src="/static/js/site_time.js?v=1" defer></script>'


def register(app):
    """Одна точка подключения. Вызывать в конце app.py."""
    app.register_blueprint(bp)

    try:
        with app.app_context():
            ensure_tables()
    except Exception as e:
        logger.warning('site_stats: ensure_tables at startup failed: %r', e)

    # 1) Старый heartbeat из base.html больше НЕ начисляет время (иначе двойной счёт
    #    с новым трекером). Он лишь отвечает, не ждёт ли пользователя опрос 25 мин.
    def _legacy_site_time():
        if not _real_user():
            return jsonify(ok=False), 401
        fb = False
        try:
            from routes.admin_support import has_pending_feedback
            fb = has_pending_feedback(current_user.id)
        except Exception:
            pass
        return jsonify(ok=True, legacy=True, feedback_pending=fb)
    if 'track_site_time' in app.view_functions:
        app.view_functions['track_site_time'] = _legacy_site_time

    # 2) Перехват готовых чертежей GeoExact → история.
    orig_status = app.view_functions.get('geoexact.status')
    if orig_status is not None:
        def _status_wrapper(*a, **kw):
            resp = orig_status(*a, **kw)
            try:
                r = resp[0] if isinstance(resp, tuple) else resp
                data = r.get_json(silent=True) if hasattr(r, 'get_json') else None
                if data and data.get('status') == 'done' and (data.get('result') or {}).get('ok') and _real_user():
                    jid = kw.get('jid') or (a[0] if a else None)
                    save_drawing(current_user.id, jid, data['result'])
            except Exception as e:
                logger.warning('geoexact status wrapper: %r', e)
            return resp
        _status_wrapper.__name__ = getattr(orig_status, '__name__', 'status')
        app.view_functions['geoexact.status'] = _status_wrapper

    # 3) Автовставка трекера в HTML-страницы (вместо правки base.html).
    @app.after_request
    def _inject_tracker(resp):
        try:
            if (resp.status_code == 200 and resp.mimetype == 'text/html'
                    and not resp.direct_passthrough and _real_user()
                    and not request.path.startswith('/static/')):
                html = resp.get_data(as_text=True)
                if INJECT_TAG not in html:
                    idx = html.rfind('</body>')
                    if idx != -1:
                        resp.set_data(html[:idx] + INJECT_TAG + html[idx:])
        except Exception as e:
            logger.debug('inject tracker skipped: %r', e)
        return resp

    logger.info('SECTION_STATS_V1 registered')
