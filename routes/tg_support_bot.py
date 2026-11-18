# -*- coding: utf-8 -*-
"""Ответ на обращение поддержки прямо из Telegram.

Владелец нажимает «Ответить» (reply) на уведомление бота: текст уходит
пользователю так же, как ответ из /admin/support (общая функция
store_admin_reply, письмо пользователю тоже уходит).

Маршрут: POST /api/tg/support-webhook — webhook Telegram Bot API.
Защита: заголовок X-Telegram-Bot-Api-Secret-Token должен совпадать с
TG_SUPPORT_WEBHOOK_SECRET, а отправитель — с SUPPORT_NOTIFY_TG_CHAT_ID.
Остальные апдейты молча игнорируются (200 OK, чтобы Telegram не повторял).

Переменные окружения:
  TELEGRAM_BOT_TOKEN, SUPPORT_NOTIFY_TG_CHAT_ID — как для уведомлений;
  TG_SUPPORT_WEBHOOK_SECRET — секрет webhook (тот же передаётся в setWebhook);
  SUPPORT_TG_ADMIN_USER_ID — необязательно: id админа в БД для атрибуции ответа.
"""
import hmac
import logging
import os
import re

from flask import Blueprint, abort, jsonify, request

from routes.admin_support import store_admin_reply
from services.telegram_notify import tg_send_text

log = logging.getLogger(__name__)

tg_support_bp = Blueprint('tg_support_bot', __name__)

_TICKET_RE = re.compile(r'Новое обращение #(\d+)')
_MAX_REPLY_LEN = 5000


def _owner_chat_id():
    return (os.environ.get('SUPPORT_NOTIFY_TG_CHAT_ID') or '').strip()


def _admin_user_id():
    raw = (os.environ.get('SUPPORT_TG_ADMIN_USER_ID') or '').strip()
    return int(raw) if raw.isdigit() else None


@tg_support_bp.route('/api/tg/support-webhook', methods=['POST'])
def tg_support_webhook():
    secret = (os.environ.get('TG_SUPPORT_WEBHOOK_SECRET') or '').strip()
    got = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if not secret or not hmac.compare_digest(got.encode('utf-8'),
                                             secret.encode('utf-8')):
        abort(403)

    update = request.get_json(silent=True) or {}
    msg = update.get('message') or {}
    owner = _owner_chat_id()
    chat_id = str((msg.get('chat') or {}).get('id', ''))
    if not owner or chat_id != owner:
        return jsonify(ok=True)

    text = (msg.get('text') or '').strip()
    replied = (msg.get('reply_to_message') or {}).get('text') or ''
    match = _TICKET_RE.search(replied)

    if not text:
        tg_send_text(owner, 'Пока принимаю только текст. '
                            'Нажмите «Ответить» на уведомление и напишите ответ.')
    elif not match:
        tg_send_text(owner, 'Чтобы ответить пользователю, нажмите «Ответить» '
                            '(reply) на уведомление об обращении.')
    elif len(text) > _MAX_REPLY_LEN:
        tg_send_text(owner, 'Ответ слишком длинный (макс %d символов).'
                     % _MAX_REPLY_LEN)
    else:
        ticket_id = int(match.group(1))
        try:
            found = store_admin_reply(ticket_id, _admin_user_id(), text)
        except Exception:
            log.exception('[tg-support] reply to #%s failed', ticket_id)
            tg_send_text(owner, 'Не удалось отправить ответ на #%d: '
                                'ошибка сервера.' % ticket_id)
        else:
            if found:
                tg_send_text(owner, 'Ответ на обращение #%d отправлен.'
                             % ticket_id)
            else:
                tg_send_text(owner, 'Обращение #%d не найдено.' % ticket_id)
    return jsonify(ok=True)
