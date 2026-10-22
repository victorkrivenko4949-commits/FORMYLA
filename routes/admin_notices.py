# -*- coding: utf-8 -*-
"""
routes/admin_notices.py — ADMIN_NOTICES_V2 (18.10.2026).

Раздел «🔔 Уведомления» для админа: простое сообщение пользователям —
от кого (Поддержка / Куратор) + текст. Каждый пользователь видит его один раз
как обычную карточку-уведомление в углу (static/js/admin_notices.js).
Отметка «показано» — в site_notice_seen с ключом 'admin:<id>'.

В таблице admin_notices: title = «Поддержка» | «Куратор» (от кого), body = текст.
Колонки link_url/link_text/targets остались от V1 и больше не заполняются.

Endpoints:
  GET  /admin/notices                      — страница: форма + список
  POST /admin/notices                      — создать (sender=support|curator, body)
  POST /admin/notices/<id>/toggle          — включить / выключить
  POST /admin/notices/<id>/delete          — удалить (вместе с отметками)
  GET  /api/admin-notices/pending          — {pending, notice:{id, sender, sender_label, body}}
  POST /api/admin-notices/seen {id}        — отметить показанным

Отключить автоподключение: ADMIN_NOTICES_AUTOREG=0.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime

from flask import (Blueprint, abort, current_app, jsonify, redirect,
                   render_template, request, session, url_for)
from flask_login import current_user, login_required
from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)

admin_notices_bp = Blueprint('admin_notices', __name__)

KEY_PREFIX = 'admin:'
MAX_BODY = 1000

SENDERS = {
    'support': 'Поддержка',
    'curator': 'Куратор',
}

_table_ready = False

_DDL_PG = """
CREATE TABLE IF NOT EXISTS admin_notices (
    id SERIAL PRIMARY KEY,
    title VARCHAR(160) NOT NULL,
    body TEXT NOT NULL,
    link_url VARCHAR(500),
    link_text VARCHAR(120),
    targets TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    activate_at TIMESTAMP,
    created_by INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""

_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS admin_notices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(160) NOT NULL,
    body TEXT NOT NULL,
    link_url VARCHAR(500),
    link_text VARCHAR(120),
    targets TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    activate_at TIMESTAMP,
    created_by INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def _ensure_activate_at_column() -> None:
    """Отложенные уведомления: добавить колонку activate_at, если её нет.

    NULL — показывать сразу; TIMESTAMP — показывать только после этого
    момента (по UTC). Нужно для запланированных анонсов.
    """
    try:
        dialect = db.engine.dialect.name
        cols = {c['name'] for c in db.session.execute(text(
            "SELECT column_name AS name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'admin_notices'"
        )).mappings()} if dialect == 'postgresql' else {
            r[1] for r in db.session.execute(text('PRAGMA table_info(admin_notices)')).all()}
        if cols and 'activate_at' not in cols:
            db.session.execute(text(
                'ALTER TABLE admin_notices ADD COLUMN activate_at TIMESTAMP'))
            db.session.commit()
    except Exception as e:  # noqa: BLE001
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.warning('[admin_notices] activate_at migration failed: %r', e)


def _ensure_table() -> None:
    global _table_ready
    if _table_ready:
        return
    try:
        from routes.site_notices import _ensure_table as _ensure_seen
        _ensure_seen()
    except Exception as e:  # noqa: BLE001
        logger.warning('[admin_notices] site_notice_seen ensure failed: %r', e)
    try:
        dialect = db.engine.dialect.name
        db.session.execute(text(_DDL_PG if dialect == 'postgresql' else _DDL_SQLITE))
        db.session.commit()
        _table_ready = True
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[admin_notices] ensure_table failed: %r', e)
    _ensure_activate_at_column()


def _is_admin() -> bool:
    return bool(current_user.is_authenticated and getattr(current_user, 'is_admin', False) is True)


def _is_real_user() -> bool:
    return bool(current_user.is_authenticated and not getattr(current_user, 'is_guest', False))


def _csrf_token() -> str:
    return session.setdefault('admin_notices_csrf', secrets.token_urlsafe(32))


def _check_csrf() -> None:
    expected = session.get('admin_notices_csrf')
    supplied = request.form.get('csrf', '') or request.headers.get('X-Admin-Notices-CSRF', '')
    if not expected or not secrets.compare_digest(expected, supplied):
        abort(403)


def _sender_key(title: str) -> str:
    t = (title or '').strip().lower()
    return 'curator' if t.startswith('куратор') else 'support'


def _row_to_notice(row) -> dict:
    key = _sender_key(row['title'])
    return {
        'id': row['id'],
        'sender': key,
        'sender_label': SENDERS[key],
        'body': row['body'],
    }


# ── Админ-страница ──────────────────────────────────────────────────────────

@admin_notices_bp.route('/admin/notices', methods=['GET'])
@login_required
def admin_page():
    if not _is_admin():
        abort(403)
    _ensure_table()
    rows = db.session.execute(text(
        'SELECT id, title, body, active, activate_at, created_at '
        'FROM admin_notices ORDER BY id DESC LIMIT 200'
    )).mappings().all()
    seen_counts = {}
    try:
        for key, cnt in db.session.execute(text(
            "SELECT notice_key, COUNT(*) FROM site_notice_seen "
            "WHERE notice_key LIKE 'admin:%' GROUP BY notice_key"
        )).all():
            seen_counts[key] = int(cnt)
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[admin_notices] seen counts failed: %r', e)
    try:
        total_users = db.session.execute(text('SELECT COUNT(*) FROM users')).scalar() or 0
    except Exception:  # noqa: BLE001
        db.session.rollback()
        total_users = 0
    notices = []
    for r in rows:
        d = dict(r)
        d['seen'] = seen_counts.get(KEY_PREFIX + str(r['id']), 0)
        d['sender'] = _sender_key(r['title'])
        notices.append(d)
    resp = current_app.make_response(render_template(
        'admin/notices.html', notices=notices, csrf=_csrf_token(),
        total_users=total_users, created=request.args.get('ok') == '1',
        senders=SENDERS,
    ))
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@admin_notices_bp.route('/admin/notices', methods=['POST'])
@login_required
def admin_create():
    if not _is_admin():
        abort(403)
    _check_csrf()
    sender = (request.form.get('sender') or 'support').strip()
    if sender not in SENDERS:
        sender = 'support'
    body = (request.form.get('body') or '').strip()[:MAX_BODY]
    if not body:
        abort(400)
    _ensure_table()
    try:
        activate_at = None
        raw_dt = (request.form.get('activate_at') or '').strip()
        if raw_dt:
            # datetime-local приходит в локальном времени админа. Сайт
            # московский — трактуем ввод как МСК и переводим в UTC
            # (сравнение в api_pending идёт с NOW() в UTC).
            from datetime import timedelta as _td
            activate_at = datetime.fromisoformat(raw_dt) - _td(hours=3)
        db.session.execute(text(
            'INSERT INTO admin_notices (title, body, link_url, link_text, targets, active, activate_at, created_by, created_at) '
            'VALUES (:t, :b, NULL, NULL, NULL, :a, :aa, :cb, :ca)'
        ), {'t': SENDERS[sender], 'b': body, 'a': True, 'aa': activate_at,
            'cb': current_user.id, 'ca': datetime.utcnow()})
        db.session.commit()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.exception('[admin_notices] create failed: %r', e)
        abort(503)
    return redirect(url_for('admin_notices.admin_page', ok=1))


@admin_notices_bp.route('/admin/notices/<int:nid>/toggle', methods=['POST'])
@login_required
def admin_toggle(nid: int):
    if not _is_admin():
        abort(403)
    _check_csrf()
    _ensure_table()
    try:
        db.session.execute(text('UPDATE admin_notices SET active = NOT active WHERE id = :id'), {'id': nid})
        db.session.commit()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.exception('[admin_notices] toggle failed: %r', e)
    return redirect(url_for('admin_notices.admin_page'))


@admin_notices_bp.route('/admin/notices/<int:nid>/delete', methods=['POST'])
@login_required
def admin_delete(nid: int):
    if not _is_admin():
        abort(403)
    _check_csrf()
    _ensure_table()
    try:
        db.session.execute(text('DELETE FROM admin_notices WHERE id = :id'), {'id': nid})
        db.session.execute(text('DELETE FROM site_notice_seen WHERE notice_key = :k'),
                           {'k': KEY_PREFIX + str(nid)})
        db.session.commit()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.exception('[admin_notices] delete failed: %r', e)
    return redirect(url_for('admin_notices.admin_page'))


# ── API для пользователей ───────────────────────────────────────────────────

@admin_notices_bp.route('/api/admin-notices/pending')
def api_pending():
    if not _is_real_user():
        return jsonify({'pending': False})
    _ensure_table()
    try:
        dialect = db.engine.dialect.name
        if dialect == 'postgresql':
            row = db.session.execute(text(
                "SELECT n.id, n.title, n.body FROM admin_notices n "
                "WHERE n.active = :a "
                "AND (n.activate_at IS NULL OR n.activate_at <= NOW()) "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM site_notice_seen s "
                "  WHERE s.user_id = :u AND s.notice_key = 'admin:' || CAST(n.id AS TEXT)) "
                "ORDER BY n.id ASC LIMIT 1"
            ), {'u': current_user.id, 'a': True}).mappings().first()
        else:
            row = db.session.execute(text(
                "SELECT n.id, n.title, n.body FROM admin_notices n "
                "WHERE n.active = :a "
                "AND (n.activate_at IS NULL OR n.activate_at <= :now) "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM site_notice_seen s "
                "  WHERE s.user_id = :u AND s.notice_key = 'admin:' || CAST(n.id AS TEXT)) "
                "ORDER BY n.id ASC LIMIT 1"
            ), {'u': current_user.id, 'a': True,
                'now': datetime.utcnow()}).mappings().first()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[admin_notices] pending failed: %r', e)
        return jsonify({'pending': False})
    resp = jsonify({'pending': True, 'notice': _row_to_notice(row)} if row else {'pending': False})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@admin_notices_bp.route('/api/admin-notices/seen', methods=['POST'])
def api_seen():
    if not _is_real_user():
        return jsonify({'ok': True})
    payload = request.get_json(silent=True) or {}
    try:
        nid = int(payload.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'bad id'}), 400
    _ensure_table()
    key = KEY_PREFIX + str(nid)
    try:
        exists = db.session.execute(text(
            'SELECT 1 FROM site_notice_seen WHERE user_id = :u AND notice_key = :k LIMIT 1'
        ), {'u': current_user.id, 'k': key}).first()
        if not exists:
            db.session.execute(text(
                'INSERT INTO site_notice_seen (user_id, notice_key, seen_at) VALUES (:u, :k, :t)'
            ), {'u': current_user.id, 'k': key, 't': datetime.utcnow()})
            db.session.commit()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[admin_notices] mark seen failed: %r', e)
    return jsonify({'ok': True})


# ── Инжектор: кнопка в шапке (админ) + скрипт карточки (все пользователи) ─────

_NAV_SCRIPT = (
    '<script id="ft-admin-notices-nav">(function(){'
    'var s=document.getElementById("navMySupportLink");'
    'var p=document.getElementById("profileNavWrap");'
    'var anchor=s||p;'
    'if(!anchor||document.getElementById("navAdminNoticesLink"))return;'
    'var a=document.createElement("a");'
    'a.id="navAdminNoticesLink";a.href="/admin/notices";'
    'a.title="Уведомления — отправить сообщение пользователям сайта";'
    'a.textContent="🔔 Уведомления";'
    'a.style.cssText="padding:8px 12px;background:rgba(244,185,66,.12);color:#fcd34d;'
    'text-decoration:none;border-radius:8px;font-weight:600;font-size:13px;'
    'border:1px solid rgba(244,185,66,.35);white-space:nowrap;transition:background .2s;";'
    'a.onmouseover=function(){a.style.background="rgba(244,185,66,.24)"};'
    'a.onmouseout=function(){a.style.background="rgba(244,185,66,.12)"};'
    'anchor.parentNode.insertBefore(a,anchor);'
    '})();</script>'
)

_USER_SCRIPT = '<script id="ft-admin-notices-script" src="/static/js/admin_notices.js?v=2" defer></script>'


def install_admin_notices(app, register=None) -> None:
    if app.extensions.get('admin_notices_installed'):
        return
    app.extensions['admin_notices_installed'] = True
    if 'admin_notices' not in app.blueprints:
        if register is None:
            app.register_blueprint(admin_notices_bp)
        else:
            register(app, admin_notices_bp)
    logger.info('[BP] admin_notices_bp registered (/admin/notices, /api/admin-notices/*)')
    print('[BP] admin_notices_bp registered (/admin/notices, /api/admin-notices/*)')

    @app.after_request
    def _admin_notices_ui(response):
        try:
            if (response.status_code != 200 or response.direct_passthrough
                    or response.mimetype != 'text/html'):
                return response
            if not current_user.is_authenticated or getattr(current_user, 'is_guest', False):
                return response
            path = request.path or ''
            if path.startswith('/intake'):
                return response
            body = response.get_data(as_text=True)
            if '</body>' not in body:
                return response
            extra = ''
            if _is_admin() and 'id="ft-admin-notices-nav"' not in body:
                extra += _NAV_SCRIPT
            if not path.startswith('/admin/notices') and 'id="ft-admin-notices-script"' not in body:
                extra += _USER_SCRIPT
            if extra:
                response.set_data(body.replace('</body>', extra + '</body>', 1))
                response.headers['Cache-Control'] = 'private, no-store'
        except Exception:  # noqa: BLE001
            pass
        return response
