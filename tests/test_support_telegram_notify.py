# -*- coding: utf-8 -*-
"""Telegram-уведомление о новом обращении в поддержку (services/telegram_notify.py)."""
import pytest

from services import telegram_notify as tn


class _FakeResp:
    def __init__(self, status_code=200, text='{"ok":true}'):
        self.status_code = status_code
        self.text = text

    @property
    def ok(self):
        return self.status_code < 400


@pytest.fixture
def tg_env(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', '123:SECRET')
    monkeypatch.setenv('SUPPORT_NOTIFY_TG_CHAT_ID', '42')
    monkeypatch.delenv('DOMAIN_URL', raising=False)
    return monkeypatch


def _call(**overrides):
    kwargs = dict(ticket_id=7, nickname='Ivan', email=None, category='bug',
                  message='<script>x</script> & y', page_url='/about',
                  has_attachments=False)
    kwargs.update(overrides)
    return tn.send_support_telegram(**kwargs)


def test_skipped_without_config(monkeypatch):
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
    monkeypatch.delenv('SUPPORT_NOTIFY_TG_CHAT_ID', raising=False)
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(args)
        return _FakeResp()

    monkeypatch.setattr('requests.post', fake_post)
    ok, err = _call()
    assert ok is False
    assert err
    assert calls == []


def test_sends_escaped_html_to_owner(tg_env):
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent.update(url=url, json=json, timeout=timeout)
        return _FakeResp()

    tg_env.setattr('requests.post', fake_post)
    ok, err = _call(email='a@b.ru', has_attachments=True)
    assert (ok, err) == (True, None)
    assert sent['url'] == 'https://api.telegram.org/bot123:SECRET/sendMessage'
    assert sent['json']['chat_id'] == '42'
    assert sent['json']['parse_mode'] == 'HTML'
    text = sent['json']['text']
    assert '&lt;script&gt;x&lt;/script&gt; &amp; y' in text
    assert 'Ivan' in text
    assert 'a@b.ru' in text
    assert 'вложения' in text
    assert sent['timeout'] == 5


def test_http_error_is_reported_not_raised(tg_env):
    tg_env.setattr('requests.post', lambda *a, **k: _FakeResp(400, 'Bad Request'))
    ok, err = _call()
    assert ok is False
    assert err == 'Telegram HTTP 400'


def test_token_is_not_leaked_in_exception(tg_env):
    def boom(*args, **kwargs):
        raise ConnectionError('Max retries exceeded with url: /bot123:SECRET/sendMessage')

    tg_env.setattr('requests.post', boom)
    ok, err = _call()
    assert ok is False
    assert 'SECRET' not in err
