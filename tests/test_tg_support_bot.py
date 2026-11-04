# -*- coding: utf-8 -*-
"""Ответ владельца на обращение из Telegram (routes/tg_support_bot.py)."""
import pytest
from flask import Flask
from sqlalchemy import text

import routes.tg_support_bot as bot
from models import db
from routes import admin_support

SECRET = 'hook-secret'
OWNER = '42'
REPLY_TO = 'Новое обращение #7 (баг)'


@pytest.fixture
def hook(monkeypatch):
    monkeypatch.setenv('TG_SUPPORT_WEBHOOK_SECRET', SECRET)
    monkeypatch.setenv('SUPPORT_NOTIFY_TG_CHAT_ID', OWNER)
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', '123:SECRET')
    monkeypatch.delenv('SUPPORT_TG_ADMIN_USER_ID', raising=False)

    state = {'sent': [], 'stored': [], 'result': True, 'error': None}

    class _Resp:
        ok = True
        status_code = 200
        text = '{"ok":true}'

    def fake_post(url, json=None, timeout=None):
        state['sent'].append(json['text'])
        return _Resp()

    def fake_store(msg_id, admin_user_id, reply_text, photo_meta=None):
        state['stored'].append((msg_id, admin_user_id, reply_text))
        if state['error']:
            raise state['error']
        return state['result']

    monkeypatch.setattr('requests.post', fake_post)
    monkeypatch.setattr(bot, 'store_admin_reply', fake_store)

    flask_app = Flask(__name__)
    flask_app.config['TESTING'] = True
    flask_app.register_blueprint(bot.tg_support_bp)
    state['client'] = flask_app.test_client()
    return state


def _update(text_msg, chat_id=OWNER, reply_to_text=None):
    msg = {'message_id': 1, 'chat': {'id': int(chat_id)}, 'text': text_msg}
    if reply_to_text is not None:
        msg['reply_to_message'] = {'message_id': 0, 'text': reply_to_text}
    return {'update_id': 1, 'message': msg}


def _post(state, payload, secret=SECRET):
    headers = {}
    if secret is not None:
        headers['X-Telegram-Bot-Api-Secret-Token'] = secret
    return state['client'].post('/api/tg/support-webhook',
                                json=payload, headers=headers)


def test_rejects_missing_or_wrong_secret(hook):
    payload = _update('Привет', reply_to_text=REPLY_TO)
    assert _post(hook, payload, secret=None).status_code == 403
    assert _post(hook, payload, secret='wrong').status_code == 403
    assert hook['stored'] == [] and hook['sent'] == []


def test_ignores_messages_from_other_chats(hook):
    resp = _post(hook, _update('Привет', chat_id='999', reply_to_text=REPLY_TO))
    assert resp.status_code == 200
    assert hook['stored'] == [] and hook['sent'] == []


def test_reply_to_notification_stores_answer(hook):
    resp = _post(hook, _update('Спасибо, всё решили', reply_to_text=REPLY_TO))
    assert resp.status_code == 200
    assert hook['stored'] == [(7, None, 'Спасибо, всё решили')]
    assert hook['sent'] == ['Ответ на обращение #7 отправлен.']


def test_plain_message_gets_hint_and_nothing_stored(hook):
    _post(hook, _update('Привет'))
    assert hook['stored'] == []
    assert 'Ответить' in hook['sent'][0]


def test_unknown_ticket_is_reported(hook):
    hook['result'] = False
    _post(hook, _update('Ответ', reply_to_text='Новое обращение #999 (вопрос)'))
    assert hook['sent'] == ['Обращение #999 не найдено.']


def test_store_error_is_reported_and_returns_200(hook):
    hook['error'] = RuntimeError('db down')
    resp = _post(hook, _update('Ответ', reply_to_text=REPLY_TO))
    assert resp.status_code == 200  # иначе Telegram будет повторять апдейт
    assert 'ошибка сервера' in hook['sent'][0]


def test_overlong_reply_is_rejected(hook):
    _post(hook, _update('я' * 5001, reply_to_text=REPLY_TO))
    assert hook['stored'] == []
    assert 'слишком длинный' in hook['sent'][0]


def test_store_admin_reply_saves_reply_for_ticket(app):
    """Общая функция пишет ответ admin в support_replies (БД тестовая, SQLite)."""
    db.session.execute(text(
        'CREATE TABLE IF NOT EXISTS support_messages ('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, '
        'user_nickname TEXT, user_email TEXT, category TEXT, message TEXT, '
        'page_url TEXT, user_agent TEXT, ip TEXT, '
        'created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'))
    db.session.execute(text(
        "INSERT INTO support_messages (user_nickname, message) "
        "VALUES ('Ivan', 'Вопрос')"))
    db.session.commit()
    ticket_id = db.session.execute(
        text('SELECT MAX(id) FROM support_messages')).scalar()

    assert admin_support.store_admin_reply(ticket_id, None, 'Ответ из Telegram') is True
    row = db.session.execute(text(
        'SELECT reply_text, sender_kind FROM support_replies '
        'WHERE support_message_id = :i'), {'i': ticket_id}).mappings().first()
    assert row['reply_text'] == 'Ответ из Telegram'
    assert row['sender_kind'] == 'admin'
    assert admin_support.store_admin_reply(999999, None, 'x') is False
