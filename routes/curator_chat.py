# -*- coding: utf-8 -*-
"""routes/curator_chat.py — чат с куратором и поддержкой (пилот Premium).

Страница /curator — два аккуратных чата:
  * Куратор — ИИ-эксперт по олимпиадам (DeepSeek), пишет первым через
    неделю после старта подписки, с fallback-сообщением при сбоях;
  * Поддержка — сообщения попадают в админ-инбокс (support_messages).

Доступно только пилотным аккаунтам (victor, Lavrik — services/pilot.py);
остальные получают 404.
"""
from __future__ import annotations

import logging

from flask import (Blueprint, abort, jsonify, render_template, request)
from flask_login import current_user, login_required

from models import db
from services.pilot import is_pilot_user

logger = logging.getLogger('formyla.curator_chat_routes')

curator_chat_bp = Blueprint('curator_chat', __name__)


def _pilot_or_404():
    if not is_pilot_user(current_user):
        abort(404)


@curator_chat_bp.route('/curator')
@login_required
def curator_page():
    _pilot_or_404()
    return render_template('curator_chat.html')


@curator_chat_bp.route('/api/curator/chat/history')
@login_required
def chat_history():
    _pilot_or_404()
    try:
        from services.curator_chat import get_history
        # Ленивый триггер недельного сообщения — НЕ ждём генерацию:
        # запускаем фоновым потоком (планировщик также делает это раз в час),
        # а историю отдаём сразу.
        try:
            import threading as _th
            from services.curator_chat import send_week1_message
            _th.Thread(target=send_week1_message, args=(current_user.id,),
                       daemon=True).start()
        except Exception:
            pass
        return jsonify({'ok': True, 'messages': get_history(current_user.id)})
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] history failed: %s', e)
        return jsonify({'ok': False, 'error': 'Не удалось загрузить чат'}), 500


@curator_chat_bp.route('/api/curator/chat', methods=['POST'])
@login_required
def chat_send():
    _pilot_or_404()
    payload = request.get_json(silent=True) or {}
    text = (payload.get('text') or '').strip()
    if not text:
        return jsonify({'ok': False, 'error': 'Пустое сообщение'}), 400
    if len(text) > 2000:
        text = text[:2000]
    try:
        from services.curator_chat import add_message, generate_reply, get_history
        add_message(current_user.id, 'user', text)
        db.session.commit()
        reply = generate_reply(current_user.id, text)
        add_message(current_user.id, 'curator', reply['content'],
                    meta={'fallback': reply.get('fallback', False)})
        db.session.commit()
        return jsonify({'ok': True, 'messages': get_history(current_user.id)})
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] send failed: %s', e)
        try:
            db.session.rollback()
        except Exception:
            pass
        # Пользователь никогда не видет «тишину»: сохраняем его сообщение
        # и отдаём fallback-ответ без обращения к модели.
        try:
            from services.curator_chat import FALLBACK_MESSAGE, add_message, get_history
            add_message(current_user.id, 'user', text)
            add_message(current_user.id, 'curator', FALLBACK_MESSAGE,
                        meta={'fallback': True})
            db.session.commit()
            return jsonify({'ok': True, 'messages': get_history(current_user.id)})
        except Exception:
            return jsonify({'ok': False, 'error': 'Сообщение не отправлено'}), 500


@curator_chat_bp.route('/api/curator/support/history')
@login_required
def support_history():
    """История переписки с поддержкой: сообщения ученика + ответы команды.

    Читает support_messages (сообщения ученика) и support_replies
    (ответы команды) — тот же инбокс, что и в админке.
    """
    _pilot_or_404()
    try:
        from sqlalchemy import text
        rows = db.session.execute(text(
            'SELECT id, message, created_at FROM support_messages '
            'WHERE user_id = :u AND COALESCE(deleted_at, \'1970-01-01\') = \'1970-01-01\' '
            'ORDER BY id DESC LIMIT 50'), {'u': current_user.id}).mappings().all()
        msg_ids = [r['id'] for r in rows]
        replies = {}
        if msg_ids:
            in_clause = ','.join(str(int(i)) for i in msg_ids)
            rep_rows = db.session.execute(text(
                f'SELECT support_message_id, reply_text, created_at '
                f'FROM support_replies WHERE support_message_id IN ({in_clause}) '
                f"AND COALESCE(deleted_at, '1970-01-01') = '1970-01-01' "
                f'ORDER BY created_at ASC')).mappings().all()
            for rp in rep_rows:
                replies.setdefault(rp['support_message_id'], []).append(rp)
        out = []
        for r in reversed(rows):  # хронология
            created = r['created_at']
            out.append({
                'role': 'user',
                'content': r['message'],
                'created_at': created.isoformat() if created else None,
            })
            for rp in replies.get(r['id'], []):
                created = rp['created_at']
                out.append({
                    'role': 'support',
                    'content': rp['reply_text'],
                    'created_at': created.isoformat() if created else None,
                })
        return jsonify({'ok': True, 'messages': out})
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] support history failed: %s', e)
        return jsonify({'ok': False, 'error': 'Не удалось загрузить историю'}), 500


@curator_chat_bp.route('/api/curator/support', methods=['POST'])
@login_required
def support_send():
    """Вкладка «Поддержка»: сообщение уходит в админ-инбокс."""
    _pilot_or_404()
    payload = request.get_json(silent=True) or {}
    text = (payload.get('text') or '').strip()
    if not text:
        return jsonify({'ok': False, 'error': 'Пустое сообщение'}), 400
    if len(text) > 2000:
        text = text[:2000]
    try:
        from sqlalchemy import text as _sql_text
        db.session.execute(_sql_text(
            'INSERT INTO support_messages '
            '(user_id, user_nickname, user_email, category, message, page_url) '
            'VALUES (:u, :n, :e, :c, :m, :p)'),
            {'u': current_user.id,
             'n': (getattr(current_user, 'nickname', None) or '')[:120],
             'e': (getattr(current_user, 'email', None) or '')[:200],
             'c': 'premium_pilot',
             'm': text,
             'p': '/curator'},
        )
        db.session.commit()
        return jsonify({'ok': True,
                        'message': 'Отправлено в поддержку — ответ придёт в этот чат.'})
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] support failed: %s', e)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'ok': False, 'error': 'Не удалось отправить'}), 500
