# -*- coding: utf-8 -*-
"""Admin support inbox + user-side support thread («Твоя поддержка»).

Маршруты:
    GET  /admin/support                 — список всех обращений + форма ответа (только админу)
    POST /admin/support/<id>/reply      — отправить ответ от админа
    GET  /my/support                    — у пользователя: его обращения + ответы админа
    POST /my/support/<id>/reply         — юзер дописывает ответ в свой тикет (двусторонний чат)
    GET  /api/my/support/unread_count   — кол-во непрочитанных ответов от админа
"""
import logging

from flask import (
    Blueprint, render_template, request, jsonify, abort, redirect,
    url_for, flash, current_app,
)
from flask_login import current_user, login_required
from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)

admin_support_bp = Blueprint('admin_support', __name__)


# ──────────────────────────────────────────────────────────────────
# AUTO-MIGRATION для таблицы support_replies
# ──────────────────────────────────────────────────────────────────
def ensure_support_replies_table():
    """Создаёт таблицу support_replies если её нет; добавляет sender_kind при апгрейде."""
    try:
        url = (current_app.config.get('SQLALCHEMY_DATABASE_URI') or '').lower()
        is_pg = url.startswith('postgresql')
        if is_pg:
            db.session.execute(text('''
                CREATE TABLE IF NOT EXISTS support_replies (
                    id SERIAL PRIMARY KEY,
                    support_message_id INTEGER NOT NULL,
                    admin_user_id INTEGER,
                    reply_text TEXT NOT NULL,
                    is_read_by_user BOOLEAN DEFAULT FALSE,
                    sender_kind VARCHAR(16) DEFAULT 'admin',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            '''))
            db.session.execute(text(
                'CREATE INDEX IF NOT EXISTS idx_support_replies_smid '
                'ON support_replies(support_message_id)'
            ))
            # ALTER для старой схемы без sender_kind
            try:
                db.session.execute(text(
                    "ALTER TABLE support_replies ADD COLUMN IF NOT EXISTS "
                    "sender_kind VARCHAR(16) DEFAULT 'admin'"
                ))
            except Exception:
                db.session.rollback()
        else:
            db.session.execute(text('''
                CREATE TABLE IF NOT EXISTS support_replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    support_message_id INTEGER NOT NULL,
                    admin_user_id INTEGER,
                    reply_text TEXT NOT NULL,
                    is_read_by_user INTEGER DEFAULT 0,
                    sender_kind TEXT DEFAULT 'admin',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            '''))
            db.session.execute(text(
                'CREATE INDEX IF NOT EXISTS idx_support_replies_smid '
                'ON support_replies(support_message_id)'
            ))
            # SQLite: проверяем колонку и добавляем если её нет
            try:
                cols = db.session.execute(text(
                    "PRAGMA table_info(support_replies)"
                )).mappings().all()
                col_names = {c['name'] for c in cols}
                if 'sender_kind' not in col_names:
                    db.session.execute(text(
                        "ALTER TABLE support_replies ADD COLUMN sender_kind TEXT DEFAULT 'admin'"
                    ))
            except Exception:
                db.session.rollback()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning('ensure_support_replies_table failed: %r', e)


def _is_admin():
    return getattr(current_user, 'is_admin', False) is True


def _build_messages(ticket_row, replies):
    """Собирает единый хронологический список сообщений тикета."""
    messages = [{
        'sender': 'user',
        'text': ticket_row.get('message') or '',
        'created_at': ticket_row.get('created_at'),
        'id': f"orig-{ticket_row.get('id')}",
    }]
    for rp in replies:
        kind = (rp.get('sender_kind') or 'admin').lower()
        if kind not in ('admin', 'user'):
            kind = 'admin'
        messages.append({
            'sender': kind,
            'text': rp.get('reply_text') or '',
            'created_at': rp.get('created_at'),
            'id': f"rep-{rp.get('id')}",
        })
    return messages


# ──────────────────────────────────────────────────────────────────
# 1) ADMIN INBOX
# ──────────────────────────────────────────────────────────────────
@admin_support_bp.route('/admin/support')
@login_required
def admin_support_inbox():
    if not _is_admin():
        abort(403)
    ensure_support_replies_table()

    rows = db.session.execute(text('''
        SELECT id, user_id, user_nickname, user_email, category, message,
               page_url, created_at
        FROM support_messages
        ORDER BY created_at DESC
        LIMIT 500
    ''')).mappings().all()

    msg_ids = [r['id'] for r in rows]
    replies_by_msg = {}
    if msg_ids:
        in_clause = ','.join(str(int(i)) for i in msg_ids)
        rep_rows = db.session.execute(text(f'''
            SELECT id, support_message_id, admin_user_id, reply_text,
                   is_read_by_user, sender_kind, created_at
            FROM support_replies
            WHERE support_message_id IN ({in_clause})
            ORDER BY created_at ASC
        ''')).mappings().all()
        for rp in rep_rows:
            replies_by_msg.setdefault(rp['support_message_id'], []).append(dict(rp))

    tickets = []
    for r in rows:
        d = dict(r)
        d['replies'] = replies_by_msg.get(r['id'], [])
        d['has_replies'] = len(d['replies']) > 0
        d['messages'] = _build_messages(d, d['replies'])
        tickets.append(d)

    return render_template('admin/support_inbox.html', tickets=tickets)


@admin_support_bp.route('/admin/support/<int:msg_id>/reply', methods=['POST'])
@login_required
def admin_support_reply(msg_id):
    if not _is_admin():
        abort(403)
    ensure_support_replies_table()

    reply_text = (request.form.get('reply_text') or '').strip()
    if not reply_text:
        flash('Введи текст ответа', 'error')
        return redirect(url_for('admin_support.admin_support_inbox'))
    if len(reply_text) > 5000:
        flash('Ответ слишком длинный (макс 5000)', 'error')
        return redirect(url_for('admin_support.admin_support_inbox'))

    src = db.session.execute(text(
        'SELECT id, user_id, user_email, user_nickname, message '
        'FROM support_messages WHERE id = :i'
    ), {'i': msg_id}).mappings().first()
    if not src:
        flash('Сообщение не найдено', 'error')
        return redirect(url_for('admin_support.admin_support_inbox'))

    db.session.execute(text('''
        INSERT INTO support_replies (support_message_id, admin_user_id, reply_text, sender_kind)
        VALUES (:smid, :aid, :txt, 'admin')
    '''), {'smid': msg_id, 'aid': current_user.id, 'txt': reply_text})
    db.session.commit()

    if src['user_email']:
        try:
            from utils.mail import send_email as resend_send, is_configured as resend_ready
            if resend_ready():
                subject = 'Ответ от поддержки FORMYLA'
                html = (
                    f'<p>Привет!</p>'
                    f'<p>На твоё обращение ответили:</p>'
                    f'<blockquote style="border-left:3px solid #38bdf8;padding-left:12px;color:#334155;">'
                    f'{_escape(reply_text)}'
                    f'</blockquote>'
                    f'<hr><p style="color:#64748b;font-size:12px;">Твой исходный вопрос: '
                    f'<em>{_escape((src["message"] or "")[:200])}</em></p>'
                    f'<p>Ответить можно прямо на сайте: <a href="{request.url_root}my/support">'
                    f'формыла.com/my/support</a></p>'
                )
                resend_send(src['user_email'], subject, html)
        except Exception as e:
            logger.warning('Failed to email user about reply: %r', e)

    flash('Ответ отправлен', 'success')
    return redirect(url_for('admin_support.admin_support_inbox'))


def _escape(s):
    """Простой HTML escape."""
    return (str(s or '')
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace('\n', '<br>'))


# ──────────────────────────────────────────────────────────────────
# 2) USER-SIDE PAGE: «Твоя поддержка»
# ──────────────────────────────────────────────────────────────────
@admin_support_bp.route('/my/support')
@login_required
def my_support_page():
    """Страница ученика: его обращения + переписка с админом (двусторонний чат)."""
    ensure_support_replies_table()
    uid = current_user.id

    rows = db.session.execute(text('''
        SELECT id, category, message, created_at
        FROM support_messages
        WHERE user_id = :uid
        ORDER BY created_at ASC
        LIMIT 200
    '''), {'uid': uid}).mappings().all()

    msg_ids = [r['id'] for r in rows]
    replies_by_msg = {}
    if msg_ids:
        in_clause = ','.join(str(int(i)) for i in msg_ids)
        rep_rows = db.session.execute(text(f'''
            SELECT id, support_message_id, reply_text, created_at,
                   is_read_by_user, sender_kind
            FROM support_replies
            WHERE support_message_id IN ({in_clause})
            ORDER BY created_at ASC
        ''')).mappings().all()
        for rp in rep_rows:
            replies_by_msg.setdefault(rp['support_message_id'], []).append(dict(rp))

        # Помечаем ВСЕ ответы админа как прочитанные (свои сообщения уже read)
        try:
            is_pg = (current_app.config.get('SQLALCHEMY_DATABASE_URI') or '').lower().startswith('postgresql')
            true_lit = 'TRUE' if is_pg else '1'
            false_lit = 'FALSE' if is_pg else '0'
            db.session.execute(text(f'''
                UPDATE support_replies SET is_read_by_user = {true_lit}
                WHERE support_message_id IN ({in_clause})
                  AND sender_kind = 'admin'
                  AND (is_read_by_user IS NULL OR is_read_by_user = {false_lit})
            '''))
            db.session.commit()
        except Exception:
            db.session.rollback()

    tickets = []
    for r in rows:
        d = dict(r)
        replies = replies_by_msg.get(r['id'], [])
        d['replies'] = replies
        d['messages'] = _build_messages(d, replies)
        # last_status: ждём ответа админа, если последнее сообщение от юзера
        last_sender = d['messages'][-1]['sender'] if d['messages'] else 'user'
        d['status'] = 'waiting' if last_sender == 'user' else 'replied'
        tickets.append(d)

    return render_template('my_support.html', tickets=tickets)


@admin_support_bp.route('/my/support/<int:msg_id>/reply', methods=['POST'])
@login_required
def my_support_reply(msg_id):
    """Юзер дописывает ответ в свой тикет (двусторонний чат)."""
    ensure_support_replies_table()

    reply_text = (request.form.get('reply_text') or '').strip()
    if not reply_text:
        flash('Введи текст сообщения', 'error')
        return redirect(url_for('admin_support.my_support_page'))
    if len(reply_text) > 5000:
        flash('Сообщение слишком длинное (макс 5000)', 'error')
        return redirect(url_for('admin_support.my_support_page'))

    # Проверяем что тикет принадлежит текущему юзеру
    src = db.session.execute(text(
        'SELECT id, user_id, user_email, user_nickname, message '
        'FROM support_messages WHERE id = :i'
    ), {'i': msg_id}).mappings().first()
    if not src:
        flash('Тикет не найден', 'error')
        return redirect(url_for('admin_support.my_support_page'))
    if src['user_id'] != current_user.id:
        abort(403)

    # INSERT user reply (is_read_by_user=True — юзер сам читал что написал)
    try:
        is_pg = (current_app.config.get('SQLALCHEMY_DATABASE_URI') or '').lower().startswith('postgresql')
        true_lit = True if is_pg else 1
        db.session.execute(text('''
            INSERT INTO support_replies
                (support_message_id, admin_user_id, reply_text, sender_kind, is_read_by_user)
            VALUES (:smid, NULL, :txt, 'user', :read)
        '''), {'smid': msg_id, 'txt': reply_text, 'read': true_lit})
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning('my_support_reply insert failed: %r', e)
        flash('Не удалось отправить сообщение', 'error')
        return redirect(url_for('admin_support.my_support_page'))

    # Опционально: уведомить админа по email
    try:
        admin_email = current_app.config.get('ADMIN_EMAIL') or current_app.config.get('SUPPORT_EMAIL')
        if admin_email:
            from utils.mail import send_email as resend_send, is_configured as resend_ready
            if resend_ready():
                subject = f'Новое сообщение в тикете #{msg_id} от {getattr(current_user, "nickname", "юзера")}'
                html = (
                    f'<p>Юзер <strong>{_escape(getattr(current_user, "nickname", "") or current_user.id)}</strong> '
                    f'дописал в тикете #{msg_id}:</p>'
                    f'<blockquote style="border-left:3px solid #38ef7d;padding-left:12px;color:#334155;">'
                    f'{_escape(reply_text)}'
                    f'</blockquote>'
                    f'<hr><p style="color:#64748b;font-size:12px;">Исходный вопрос: '
                    f'<em>{_escape((src["message"] or "")[:200])}</em></p>'
                    f'<p><a href="{request.url_root}admin/support">Открыть инбокс</a></p>'
                )
                resend_send(admin_email, subject, html)
    except Exception as e:
        logger.warning('Failed to email admin about user reply: %r', e)

    flash('Сообщение отправлено', 'success')
    return redirect(url_for('admin_support.my_support_page'))


@admin_support_bp.route('/api/my/support/messages')
@login_required
def my_support_messages_api():
    """Возвращает ВСЕ сообщения текущего юзера + ответы админа.

    Используется виджетом «Связаться с нами» на /about для:
    1) Восстановления истории при загрузке страницы (persistence).
    2) Polling-а каждые ~15 сек — чтобы видеть ответы админа без перезагрузки.

    Формат ответа:
        {
          "success": true,
          "messages": [
            {"from": "user"|"admin", "text": "...",
             "created_at": "ISO8601", "ticket_id": int, "id": "orig-..."|"rep-..."},
            ...
          ]
        }
    Сортировка — хронологическая (ASC) по created_at.
    """
    ensure_support_replies_table()
    uid = current_user.id

    try:
        ticket_rows = db.session.execute(text('''
            SELECT id, category, message, created_at
            FROM support_messages
            WHERE user_id = :uid
            ORDER BY created_at ASC
            LIMIT 500
        '''), {'uid': uid}).mappings().all()

        msg_ids = [r['id'] for r in ticket_rows]
        rep_rows = []
        if msg_ids:
            in_clause = ','.join(str(int(i)) for i in msg_ids)
            rep_rows = db.session.execute(text(f'''
                SELECT id, support_message_id, reply_text, created_at, sender_kind
                FROM support_replies
                WHERE support_message_id IN ({in_clause})
                ORDER BY created_at ASC
            ''')).mappings().all()

        all_msgs = []
        for m in ticket_rows:
            ts = m['created_at']
            all_msgs.append({
                'id': f"orig-{m['id']}",
                'from': 'user',
                'text': m['message'] or '',
                'created_at': ts.isoformat() if hasattr(ts, 'isoformat') else (str(ts) if ts else ''),
                'ticket_id': m['id'],
            })
        for r in rep_rows:
            kind = (r['sender_kind'] or 'admin').lower()
            if kind not in ('admin', 'user'):
                kind = 'admin'
            ts = r['created_at']
            all_msgs.append({
                'id': f"rep-{r['id']}",
                'from': kind,
                'text': r['reply_text'] or '',
                'created_at': ts.isoformat() if hasattr(ts, 'isoformat') else (str(ts) if ts else ''),
                'ticket_id': r['support_message_id'],
            })

        all_msgs.sort(key=lambda x: x['created_at'] or '')

        # Помечаем все ответы админа как прочитанные (раз юзер их сейчас увидит)
        if msg_ids:
            try:
                is_pg = (current_app.config.get('SQLALCHEMY_DATABASE_URI') or '').lower().startswith('postgresql')
                true_lit = 'TRUE' if is_pg else '1'
                false_lit = 'FALSE' if is_pg else '0'
                in_clause = ','.join(str(int(i)) for i in msg_ids)
                db.session.execute(text(f'''
                    UPDATE support_replies SET is_read_by_user = {true_lit}
                    WHERE support_message_id IN ({in_clause})
                      AND sender_kind = 'admin'
                      AND (is_read_by_user IS NULL OR is_read_by_user = {false_lit})
                '''))
                db.session.commit()
            except Exception:
                db.session.rollback()

        return jsonify({'success': True, 'messages': all_msgs})
    except Exception as e:
        logger.warning('my_support_messages_api failed: %r', e)
        return jsonify({'success': False, 'messages': [], 'error': str(e)}), 500


@admin_support_bp.route('/api/my/support/unread_count')
@login_required
def my_support_unread_count():
    """Сколько непрочитанных ответов от админа у текущего юзера."""
    ensure_support_replies_table()
    try:
        is_pg = (current_app.config.get('SQLALCHEMY_DATABASE_URI') or '').lower().startswith('postgresql')
        false_lit = 'FALSE' if is_pg else '0'
        result = db.session.execute(text(f'''
            SELECT COUNT(*) AS cnt FROM support_replies sr
            JOIN support_messages sm ON sm.id = sr.support_message_id
            WHERE sm.user_id = :uid
              AND sr.sender_kind = 'admin'
              AND (sr.is_read_by_user IS NULL OR sr.is_read_by_user = {false_lit})
        '''), {'uid': current_user.id}).scalar()
        return jsonify({'unread': int(result or 0)})
    except Exception as e:
        logger.warning('unread_count failed: %r', e)
        return jsonify({'unread': 0})
