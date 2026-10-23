# -*- coding: utf-8 -*-
"""Вечернее напоминание о задачах дня (daily_quest_deadline_reminder_job).

Проверяем без БД/планировщика: логика выбора адресата дайджеста и
тексты писем в services.email_service.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def _env(monkeypatch, **kw):
    for k, v in kw.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)


def test_deadline_email_subject_and_link(monkeypatch):
    """Письмо содержит часы и ссылку на задачи дня."""
    from services import email_service

    sent = {}

    class _User:
        email = 'kid@example.com'
        nickname = 'kid'

    def fake_send(to, subject, html, text_content=None, to_name=None):
        sent['to'] = to
        sent['subject'] = subject
        sent['html'] = html
        return True

    monkeypatch.setattr(email_service, 'send_email', fake_send)
    ok = email_service.send_daily_tasks_deadline(_User(), hours_left=5)
    assert ok is True
    assert sent['to'] == 'kid@example.com'
    assert '5' in sent['subject']
    assert 'formyla.net/daily_tasks' in sent['html']
    assert 'kid' in sent['html']


def test_deadline_email_no_address(monkeypatch):
    """Без email у пользователя — письмо не шлётся и не падает."""
    from services import email_service

    class _User:
        email = None
        nickname = 'ghost'

    calls = []
    monkeypatch.setattr(
        email_service, 'send_email',
        lambda *a, **kw: calls.append(a) or True,
    )
    assert email_service.send_daily_tasks_deadline(_User()) is False
    assert calls == []


def test_digest_lists_recipients_and_skips_when_empty(monkeypatch):
    """Дайджест владельцу: список должников; пустой список — не шлём."""
    from services import email_service

    sent = {}

    def fake_send(to, subject, html, text_content=None, to_name=None):
        sent['to'] = to
        sent['html'] = html
        return True

    monkeypatch.setattr(email_service, 'send_email', fake_send)

    # пустой список должников — ничего не шлём
    assert email_service.send_daily_tasks_deadline_digest(
        'admin@example.com', total_pending=0, recipients=[]) is False
    assert sent == {}

    recips = [
        {'id': 9120, 'name': 'Диана', 'email': 'd@example.com'},
        {'id': 9121, 'name': None, 'email': 'k@example.com'},
    ]
    ok = email_service.send_daily_tasks_deadline_digest(
        'admin@example.com', total_pending=2, recipients=recips, hours_left=3)
    assert ok is True
    assert sent['to'] == 'admin@example.com'
    assert '#9120' in sent['html']
    assert 'd@example.com' in sent['html']
    assert 'k@example.com' in sent['html']
    assert '3' in sent['html']  # hours_left
